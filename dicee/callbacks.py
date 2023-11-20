import datetime
import time
import numpy as np
import torch

import dicee.models.base_model
from .static_funcs import save_checkpoint_model, exponential_function, save_pickle
from .abstracts import AbstractCallback, AbstractPPECallback
import pandas as pd


class AccumulateEpochLossCallback(AbstractCallback):
    def __init__(self, path: str):
        super().__init__()
        self.path = path

    def on_fit_end(self, trainer, model) -> None:
        """
        Store epoch loss


        Parameter
        ---------
        trainer:

        model:

        Returns
        ---------
        None
        """
        pd.DataFrame(model.loss_history, columns=['EpochLoss']).to_csv(f'{self.path}/epoch_losses.csv')


class PrintCallback(AbstractCallback):
    def __init__(self):
        super().__init__()
        self.start_time = time.time()

    def on_fit_start(self, trainer, pl_module):
        print(pl_module)
        print(pl_module.summarize())
        print(pl_module.selected_optimizer)
        print(f"\nTraining is starting {datetime.datetime.now()}...")

    def on_fit_end(self, trainer, pl_module):
        training_time = time.time() - self.start_time
        if 60 > training_time:
            message = f'{training_time:.3f} seconds.'
        elif 60 * 60 > training_time > 60:
            message = f'{training_time / 60:.3f} minutes.'
        elif training_time > 60 * 60:
            message = f'{training_time / (60 * 60):.3f} hours.'
        else:
            message = f'{training_time:.3f} seconds.'
        print(f"Training Runtime: {message}\n")

    def on_train_batch_end(self, *args, **kwargs):
        return

    def on_train_epoch_end(self, *args, **kwargs):
        return


class KGESaveCallback(AbstractCallback):
    def __init__(self, every_x_epoch: int, max_epochs: int, path: str):
        super().__init__()
        self.every_x_epoch = every_x_epoch
        self.max_epochs = max_epochs
        self.epoch_counter = 0
        self.path = path
        if self.every_x_epoch is None:
            self.every_x_epoch = max(self.max_epochs // 2, 1)

    def on_train_batch_end(self, *args, **kwargs):
        return

    def on_fit_start(self, trainer, pl_module):
        pass

    def on_train_epoch_end(self, *args, **kwargs):
        pass

    def on_fit_end(self, *args, **kwargs):
        pass

    def on_epoch_end(self, model, trainer, **kwargs):
        if self.epoch_counter % self.every_x_epoch == 0 and self.epoch_counter > 1:
            print(f'\nStoring model {self.epoch_counter}...')
            save_checkpoint_model(model,
                                  path=self.path + f'/model_at_{str(self.epoch_counter)}_'
                                                   f'epoch_{str(str(datetime.datetime.now()))}.pt')
        self.epoch_counter += 1


class PseudoLabellingCallback(AbstractCallback):
    def __init__(self, data_module, kg, batch_size):
        super().__init__()
        self.data_module = data_module
        self.kg = kg
        self.num_of_epochs = 0
        self.unlabelled_size = len(self.kg.unlabelled_set)
        self.batch_size = batch_size

    def create_random_data(self):
        entities = torch.randint(low=0, high=self.kg.num_entities, size=(self.batch_size, 2))
        relations = torch.randint(low=0, high=self.kg.num_relations, size=(self.batch_size,))
        # unlabelled triples
        return torch.stack((entities[:, 0], relations, entities[:, 1]), dim=1)

    def on_epoch_end(self, trainer, model):
        # Create random triples
        # if trainer.current_epoch < 10:
        #    return None
        # Increase it size, Now we increase it.
        model.eval()
        with torch.no_grad():
            # (1) Create random triples
            # unlabelled_input_batch = self.create_random_data()
            # (2) or use unlabelled batch
            unlabelled_input_batch = self.kg.unlabelled_set[
                torch.randint(low=0, high=self.unlabelled_size, size=(self.batch_size,))]
            # (2) Predict unlabelled batch, and use prediction as pseudo-labels
            pseudo_label = torch.sigmoid(model(unlabelled_input_batch))
            selected_triples = unlabelled_input_batch[pseudo_label >= .90]
        if len(selected_triples) > 0:
            # Update dataset
            self.data_module.train_set_idx = np.concatenate(
                (self.data_module.train_set_idx, selected_triples.detach().numpy()),
                axis=0)
            trainer.train_dataloader = self.data_module.train_dataloader()
            print(f'\tEpoch:{trainer.current_epoch}: Pseudo-labelling\t |D|= {len(self.data_module.train_set_idx)}')
        model.train()


def estimate_q(eps):
    """ estimate rate of convergence q from sequence esp"""
    x = np.arange(len(eps) - 1)
    y = np.log(np.abs(np.diff(np.log(eps))))
    line = np.polyfit(x, y, 1)  # fit degree 1 polynomial
    q = np.exp(line[0])  # find q
    return q


def compute_convergence(seq, i):
    assert len(seq) >= i > 0
    return estimate_q(seq[-i:] / (np.arange(i) + 1))


class PPE(AbstractPPECallback):
    """ A callback for Polyak Parameter Ensemble Technique
        Maintains a running parameter average for all parameters requiring gradient signals
    """

    def __init__(self, num_epochs: int, path: str,
                 epoch_to_start: int = None, last_percent_to_consider=None):
        assert isinstance(num_epochs, int)
        assert isinstance(path, str)
        super().__init__(num_epochs, path, epoch_to_start, last_percent_to_consider)
        # self.alphas = np.ones(self.num_ensemble_coefficient) / self.num_ensemble_coefficient

    def initialize_ensemble(self, model):
        torch.save(model.state_dict(), f=f"{self.path}/trainer_checkpoint_main.pt")
        return torch.load(f"{self.path}/trainer_checkpoint_main.pt", torch.device(model.device))

    def should_averaging_start(self):
        return self.epoch_to_start <= self.epoch_count

    def get_ensemble_model(self, model):
        if self.sample_counter == 0:
            self.sample_counter += 1
            torch.save(model.state_dict(), f=f"{self.path}/trainer_checkpoint_main.pt")
        return torch.load(f"{self.path}/trainer_checkpoint_main.pt", torch.device(model.device))

    def update_ensemble(self, ensemble_state_dict, current_model):
        with torch.no_grad():
            for k, parameters in current_model.state_dict().items():
                if parameters.dtype == torch.float:
                    # ensemble_state_dict[k] += self.alphas[self.sample_counter] * parameters
                    ensemble_state_dict[k] = (ensemble_state_dict[k] * self.sample_counter + parameters) / (
                            1 + self.sample_counter)

    def on_train_epoch_end(self, trainer, model) -> None:
        self.epoch_count += 1
        if self.should_averaging_start():
            # Load the ensemble model
            ensemble_state_dict = self.get_ensemble_model(model=model)
            # Update the ensemble model
            self.update_ensemble(ensemble_state_dict=ensemble_state_dict, current_model=model)
            # Store the ensemble model
            self.store_ensemble(ensemble_state_dict)


class ASWA(AbstractPPECallback):
    """ Adaptive stochastic weight averaging
        ASWE keeps track of the validation performance and update s the ensemble model accordingly.
        """

    def __init__(self, num_epochs, path):
        super().__init__(num_epochs, path, epoch_to_start=None, last_percent_to_consider=None)
        self.reports_of_running_model = []
        self.reports_of_ensemble_model = []
        self.last_mrr_ensemble = None
        self.initial_eval_setting = None
        self.entered_good_regions = None
        self.alphas = None
        self.val_aswa=-1

    def on_fit_end(self, trainer, model):
        """

        Parameters
        ----------
        trainer
        model

        Returns
        -------

        """
        super().on_fit_end(trainer, model)
        if self.initial_eval_setting:
            # ADD this info back
            trainer.evaluator.args.eval_model = self.initial_eval_setting

        # @TODO
        """
        
        running_mrr = []
        ensemble_mrr = []

        for ith_epoch in range(len(self.reports_of_running_model)):
            running_mrr.append(self.reports_of_running_model[ith_epoch]["Val"]["MRR"])

        plt.plot(running_mrr, label="Running")

        # Need to start from somwhere
        for i in range(len(self.reports_of_ensemble_model)):
            ensemble_mrr.append(self.reports_of_ensemble_model[i]["Val"]["MRR"])
        plt.plot(ensemble_mrr, label="ASWE")
        plt.legend()
        plt.grid()
        plt.show()
        """

    @staticmethod
    def __compute_mrr(trainer, model) -> float:
        # (2) Enable eval mode.
        model.eval()
        # (3) MRR performance on the validation data of running model.
        device_name=model.device
        model.to("cpu")
        last_val_mrr_running_model = trainer.evaluator.eval(dataset=trainer.dataset,
                                                            trained_model=model,
                                                            form_of_labelling=trainer.form_of_labelling,
                                                            during_training=True)["Val"]["MRR"]
        model.to(device_name)
        # (4) Enable train mode.
        model.train()
        return last_val_mrr_running_model

    def is_mrr_increasing(self, trainer, model) -> bool:

        last_val_mrr_running_model = self.__compute_mrr(trainer, model)
        self.reports_of_running_model.append(last_val_mrr_running_model)
        # (4) Does the validation performance of running model still increase?
        if self.last_mrr_ensemble is None:
            loss, loss_counter = 0.0, 0
            # (5.1) Iterate over the most recent 10 MRR scores
            for idx, mrr in enumerate(self.reports_of_running_model[-10:]):
                if last_val_mrr_running_model > mrr:
                    """No loss"""
                else:
                    loss += (last_val_mrr_running_model - mrr) ** 2
                    loss_counter += 1
            # (5.2) If the last MRR performance of the running model is greater than 50% of the previous epochs,
            # then do not initialize the ensemble
            if loss_counter >= 5:
                return False
            else:
                return True
        else:
            return False

    def initialize_or_load_ensemble(self, model):
        # (6) Validation performance decreased: Shall we update the ensemble model with the current running model ?
        # (6.1) Initialize parameter ensemble model via the current running model, if it is not initialized.
        if self.sample_counter == 0:
            torch.save(model.state_dict(), f=f"{self.path}/trainer_checkpoint_main.pt")
            self.sample_counter += 1
        else:
            """ No action"""

        return torch.load(f"{self.path}/trainer_checkpoint_main.pt", torch.device(model.device))

    def inplace_update_parameter_ensemble(self, ensemble_state_dict, current_model) -> None:
        with torch.no_grad():
            for k, parameters in current_model.state_dict().items():
                if parameters.dtype == torch.float:
                    # (2) Update the parameter ensemble model with the current model.
                    # Moving average
                    ensemble_state_dict[k] = (ensemble_state_dict[k] * self.sample_counter + parameters) / (
                            1 + self.sample_counter)

    def store_ensemble_model(self, ensemble_state_dict, mrr_updated_ensemble_model) -> None:
        if self.last_mrr_ensemble is None:
            self.last_mrr_ensemble = mrr_updated_ensemble_model
            self.sample_counter += 1
            torch.save(ensemble_state_dict, f=f"{self.path}/trainer_checkpoint_main.pt")
        else:
            if mrr_updated_ensemble_model > self.last_mrr_ensemble:
                print(f"ASWA ensemble updated: Current MRR: {mrr_updated_ensemble_model}")
                self.last_mrr_ensemble = mrr_updated_ensemble_model
                self.sample_counter += 1
                torch.save(ensemble_state_dict, f=f"{self.path}/trainer_checkpoint_main.pt")
            else:
                """ Rejection of updating the parameter ensemble with the current running model"""

    def on_train_epoch_end(self, trainer, model):
        # (1) Increment epoch counter
        self.epoch_count += 1
        # (2) Save the given eval setting .
        if self.initial_eval_setting is None:
            self.initial_eval_setting = trainer.evaluator.args.eval_model
            trainer.evaluator.args.eval_model = "val"

        val_running_model = self.__compute_mrr(trainer, model)
        if val_running_model > self.val_aswa:
            # hard update
            self.val_aswa= val_running_model
            torch.save(model.state_dict(), f=f"{self.path}/trainer_checkpoint_main.pt")
            self.sample_counter = 1
            print(f"Hard Update: MRR: {self.val_aswa}")
        else:
            # Load ensemble
            ensemble_state_dict = torch.load(f"{self.path}/trainer_checkpoint_main.pt", torch.device(model.device))
            # Perform provision parameter update.
            with torch.no_grad():
                for k, parameters in model.state_dict().items():
                    if parameters.dtype == torch.float:
                        ensemble_state_dict[k] = (ensemble_state_dict[k] * self.sample_counter + parameters) / (1 + self.sample_counter)
            # Evaluate
            ensemble = type(model)(model.args)
            ensemble.load_state_dict(ensemble_state_dict)
            mrr_updated_ensemble_model = trainer.evaluator.eval(dataset=trainer.dataset, trained_model=ensemble,
                                                                form_of_labelling=trainer.form_of_labelling,
                                                                during_training=True)["Val"]["MRR"]

            if mrr_updated_ensemble_model > self.val_aswa:

                self.val_aswa = mrr_updated_ensemble_model
                torch.save(ensemble_state_dict, f=f"{self.path}/trainer_checkpoint_main.pt")
                self.sample_counter += 1
                print(f" Soft Update: MRR: {self.val_aswa} | |ASWA|:{self.sample_counter}")
            else:
                print(" No update")

class FPPE(AbstractPPECallback):
    """
    import matplotlib.pyplot as plt
    import numpy as np
    def exponential_function(x: np.ndarray, lam: float, ascending_order=True) -> torch.FloatTensor:
        # A sequence in exponentially decreasing order
        result = np.exp(-lam * x) / np.sum(np.exp(-lam * x))
        assert 0.999 < sum(result) < 1.0001
        result = np.flip(result) if ascending_order else result
        return torch.tensor(result.tolist())

    N = 100
    equal_weights = np.ones(N) / N
    plt.plot(equal_weights, 'r', label="Equal")
    plt.plot(exponential_function(np.arange(N), lam=0.1,), 'c-', label="Exp. forgetful with 0.1")
    plt.plot(exponential_function(np.arange(N), lam=0.05), 'g-', label="Exp. forgetful with 0.05")
    plt.plot(exponential_function(np.arange(N), lam=0.025), 'b-', label="Exp. forgetful with 0.025")
    plt.plot(exponential_function(np.arange(N), lam=0.01), 'k-', label="Exp. forgetful with 0.01")
    plt.title('Ensemble coefficients')
    plt.xlabel('Epochs')
    plt.ylabel('Coefficients')
    plt.legend()
    plt.savefig('ensemble_coefficients.pdf')
    plt.show()
    """

    def __init__(self, num_epochs, path, last_percent_to_consider=None):
        super().__init__(num_epochs, path, last_percent_to_consider)
        lamb = 0.1
        self.alphas = exponential_function(np.arange(self.num_ensemble_coefficient), lam=lamb, ascending_order=True)
        print(f"Forgetful Ensemble Coefficients with lambda {lamb}:", self.alphas)


class Eval(AbstractCallback):
    def __init__(self, path, epoch_ratio: int = None):
        super().__init__()
        self.path = path
        self.reports = []
        self.epoch_ratio = epoch_ratio if epoch_ratio is not None else 1
        self.epoch_counter = 0

    def on_fit_start(self, trainer, model):
        pass

    def on_fit_end(self, trainer, model):
        save_pickle(data=self.reports, file_path=trainer.attributes.full_storage_path + '/evals_per_epoch')
        """

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7, 7))
        for (p,q), mrr in pairs_to_train_mrr.items():
            ax1.plot(mrr, label=f'{p},{q}')
        ax1.set_ylabel('Train MRR')

        for (p,q), mrr in pairs_to_val_mrr.items():
            ax2.plot(mrr, label=f'{p},{q}')
        ax2.set_ylabel('Val MRR')

        plt.legend()
        plt.xlabel('Epochs')
        plt.savefig('{full_storage_path}train_val_mrr.pdf')
        plt.show()
        """

    def on_train_epoch_end(self, trainer, model):
        self.epoch_counter += 1
        if self.epoch_counter % self.epoch_ratio == 0:
            model.eval()
            report = trainer.evaluator.eval(dataset=trainer.dataset, trained_model=model,
                                            form_of_labelling=trainer.form_of_labelling, during_training=True)
            model.train()
            self.reports.append(report)

    def on_train_batch_end(self, *args, **kwargs):
        return


class KronE(AbstractCallback):
    def __init__(self):
        super().__init__()
        self.f = None

    @staticmethod
    def batch_kronecker_product(a, b):
        """
        Kronecker product of matrices a and b with leading batch dimensions.
        Batch dimensions are broadcast. The number of them mush
        :type a: torch.Tensor
        :type b: torch.Tensor
        :rtype: torch.Tensor
        """

        a, b = a.unsqueeze(1), b.unsqueeze(1)

        siz1 = torch.Size(torch.tensor(a.shape[-2:]) * torch.tensor(b.shape[-2:]))
        res = a.unsqueeze(-1).unsqueeze(-3) * b.unsqueeze(-2).unsqueeze(-4)
        siz0 = res.shape[:-4]
        res = res.reshape(siz0 + siz1)
        return res.flatten(1)

    def get_kronecker_triple_representation(self, indexed_triple: torch.LongTensor):
        """
        Get kronecker embeddings
        """
        n, d = indexed_triple.shape
        assert d == 3
        # Get the embeddings
        head_ent_emb, rel_ent_emb, tail_ent_emb = self.f(indexed_triple)

        head_ent_kron_emb = self.batch_kronecker_product(*torch.hsplit(head_ent_emb, 2))
        rel_ent_kron_emb = self.batch_kronecker_product(*torch.hsplit(rel_ent_emb, 2))
        tail_ent_kron_emb = self.batch_kronecker_product(*torch.hsplit(tail_ent_emb, 2))

        return torch.cat((head_ent_emb, head_ent_kron_emb), dim=1), \
            torch.cat((rel_ent_emb, rel_ent_kron_emb), dim=1), \
            torch.cat((tail_ent_emb, tail_ent_kron_emb), dim=1)

    def on_fit_start(self, trainer, model):
        if isinstance(model.normalize_head_entity_embeddings, dicee.models.base_model.IdentityClass):
            self.f = model.get_triple_representation
            model.get_triple_representation = self.get_kronecker_triple_representation

        else:
            raise NotImplementedError('Normalizer should be reinitialized')


class Perturb(AbstractCallback):
    """ A callback for a three-Level Perturbation

    Input Perturbation: During training an input x is perturbed by randomly replacing its element.
    In the context of knowledge graph embedding models, x can denote a triple, a tuple of an entity and a relation,
    or a tuple of two entities.
    A perturbation means that a component of x is randomly replaced by an entity or a relation.

    Parameter Perturbation:

    Output Perturbation:
    """

    def __init__(self, level: str = "input", ratio: float = 0.0, method: str = None, scaler: float = None,
                 frequency=None):
        """
        level in {input, param, output}
        ratio:float btw [0,1] a percentage of mini-batch data point to be perturbed.
        method = ?
        """
        super().__init__()

        assert level in {"input", "param", "out"}
        assert ratio >= 0.0
        self.level = level
        self.ratio = ratio
        self.method = method
        self.scaler = scaler
        self.frequency = frequency  # per epoch, per mini-batch ?

    def on_train_batch_start(self, trainer, model, batch, batch_idx):
        # Modifications should be in-place
        # (1) Extract the input and output data points in a given batch.
        x, y = batch
        n, _ = x.shape
        assert n > 0
        # (2) Compute the number of perturbed data points.
        num_of_perturbed_data = int(n * self.ratio)
        if num_of_perturbed_data == 0:
            return None
        # (3) Detect the device on which data points reside
        device = x.get_device()
        if device == -1:
            device = "cpu"
        # (4) Sample random integers from 0 to n without replacement and take num_of_perturbed_data of tem
        random_indices = torch.randperm(n, device=device)[:num_of_perturbed_data]
        # (5) Apply perturbation depending on the level.

        # (5.1) Apply Input level perturbation.
        if self.level == "input":
            if torch.rand(1) > 0.5:
                # (5.1.1) Perturb input via heads: Sample random indices for heads.
                perturbation = torch.randint(low=0, high=model.num_entities,
                                             size=(num_of_perturbed_data,),
                                             device=device)
                # Replace the head entities with (5.1.1) on given randomly selected data points in a mini-batch.
                x[random_indices] = torch.column_stack((perturbation, x[:, 1][random_indices]))
            else:
                # (5.1.2) Perturb input via relations : Sample random indices for relations.
                perturbation = torch.randint(low=0, high=model.num_relations,
                                             size=(num_of_perturbed_data,),
                                             device=device)
                # Replace the relations with (5.1.2) on given randomly selected data points in a mini-batch.
                x[random_indices] = torch.column_stack(
                    (x[:, 0][random_indices], perturbation))
        # (5.2) Apply Parameter level perturbation.
        elif self.level == "param":
            h, r = torch.hsplit(x, 2)
            # (5.2.1) Apply Gaussian Perturbation
            if self.method == "GN":
                if torch.rand(1) > 0.0:
                    # (5.2.1.1) Apply Gaussian Perturbation on heads.
                    h_selected = h[random_indices]
                    with torch.no_grad():
                        model.entity_embeddings.weight[h_selected] += torch.normal(mean=0, std=self.scaler,
                                                                                   size=model.entity_embeddings.weight[
                                                                                       h_selected].shape,
                                                                                   device=model.device)
                else:
                    # (5.2.1.2) Apply Gaussian Perturbation on relations.
                    r_selected = r[random_indices]
                    with (torch.no_grad()):
                        model.relation_embeddings.weight[r_selected] += torch.normal(mean=0, std=self.scaler,
                                                                                     size=
                                                                                     model.entity_embeddings.weight[
                                                                                         r_selected].shape,
                                                                                     device=model.device)
            # (5.2.2) Apply Random Perturbation
            elif self.method == "RN":
                if torch.rand(1) > 0.0:
                    # (5.2.2.1) Apply Random Perturbation on heads.
                    h_selected = h[random_indices]
                    with torch.no_grad():
                        model.entity_embeddings.weight[h_selected] += torch.rand(
                            size=model.entity_embeddings.weight[h_selected].shape, device=model.device) * self.scaler
                else:
                    # (5.2.2.2) Apply Random Perturbation on relations.
                    r_selected = r[random_indices]
                    with torch.no_grad():
                        model.relation_embeddings.weight[r_selected] += torch.rand(
                            size=model.entity_embeddings.weight[r_selected].shape, device=model.device) * self.scaler
            else:
                raise RuntimeError(f"--method is given as {self.method}!")
        elif self.level == "out":
            # (5.3) Apply output level perturbation.
            if self.method == "Soft":
                # (5.3) Output level soft perturbation resembles label smoothing.
                # (5.3.1) Compute the perturbation rate.
                perturb = torch.rand(1, device=model.device) * self.scaler
                # https://pytorch.org/docs/stable/generated/torch.where.html
                # 1.0 => 1.0 - perturb
                # 0.0 => perturb
                # (5.3.2) Reduces 1s and increases 0s via (5.2.1)
                batch[1][random_indices] = torch.where(batch[1][random_indices] == 1.0, 1.0 - perturb, perturb)
            elif self.method == "Hard":
                # (5.3) Output level hard perturbation flips 1s to 0 and 0s to 1s.
                batch[1][random_indices] = torch.where(batch[1][random_indices] == 1.0, 0.0, 1.0)
            else:
                raise NotImplementedError(f"{self.level}")
        else:
            raise RuntimeError(f"--level is given as {self.level}!")

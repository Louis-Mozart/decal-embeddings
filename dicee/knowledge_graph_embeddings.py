import os.path
from typing import List, Tuple, Set, Iterable, Dict, Union
import torch
from torch import optim
from torch.utils.data import DataLoader
from .abstracts import BaseInteractiveKGE
from .dataset_classes import TriplePredictionDataset
from .static_funcs import random_prediction, deploy_triple_prediction, deploy_tail_entity_prediction, \
    deploy_relation_prediction, deploy_head_entity_prediction, load_pickle
from .static_funcs_training import evaluate_lp
from .static_preprocess_funcs import create_constraints
import numpy as np
import sys


class KGE(BaseInteractiveKGE):
    """ Knowledge Graph Embedding Class for interactive usage of pre-trained models"""

    # @TODO: we can download the model if it is not present locally
    def __init__(self, path, construct_ensemble=False,
                 model_name=None,
                 apply_semantic_constraint=False):
        super().__init__(path=path, construct_ensemble=construct_ensemble, model_name=model_name)
        # See https://numpy.org/doc/stable/reference/generated/numpy.memmap.html
        # If file exists
        if os.path.exists(path + '/train_set.npy'):
            self.train_set = np.load(file=path + '/train_set.npy', mmap_mode='r')

        if apply_semantic_constraint:
            (self.domain_constraints_per_rel, self.range_constraints_per_rel,
             self.domain_per_rel, self.range_per_rel) = create_constraints(self.train_set)

    def __str__(self):
        return "KGE | " + str(self.model)

    def eval_lp_performance(self, dataset=List[Tuple[str, str, str]], filtered=True):
        assert isinstance(dataset, list) and len(dataset) > 0

        idx_dataset = np.array(
            [(self.entity_to_idx[s], self.relation_to_idx[p], self.entity_to_idx[o]) for s, p, o in dataset])
        if filtered:
            return evaluate_lp(model=self.model, triple_idx=idx_dataset, num_entities=len(self.entity_to_idx),
                               er_vocab=load_pickle(self.path + '/er_vocab.p'),
                               re_vocab=load_pickle(self.path + '/re_vocab.p'))
        else:
            return evaluate_lp(model=self.model, triple_idx=idx_dataset, num_entities=len(self.entity_to_idx),
                               er_vocab=None, re_vocab=None)

    def predict_missing_head_entity(self, relation: List[str], tail_entity: List[str]) -> Tuple:
        """
        Given a relation and a tail entity, return top k ranked head entity.

        argmax_{e \in E } f(e,r,t), where r \in R, t \in E.

        Parameter
        ---------
        relation: List[str]

        String representation of selected relations.

        tail_entity: List[str]

        String representation of selected entities.


        k: int

        Highest ranked k entities.

        Returns: Tuple
        ---------

        Highest K scores and entities
        """

        head_entity = torch.arange(0, len(self.entity_to_idx))
        relation = torch.LongTensor([self.relation_to_idx[i] for i in relation])
        tail_entity = torch.LongTensor([self.entity_to_idx[i] for i in tail_entity])
        x = torch.stack((head_entity,
                         relation.repeat(self.num_entities, ),
                         tail_entity.repeat(self.num_entities, )), dim=1)
        return self.model.forward(x)

    def predict_missing_relations(self, head_entity: List[str], tail_entity: List[str]) -> Tuple:
        """
        Given a head entity and a tail entity, return top k ranked relations.

        argmax_{r \in R } f(h,r,t), where h, t \in E.


        Parameter
        ---------
        head_entity: List[str]

        String representation of selected entities.

        tail_entity: List[str]

        String representation of selected entities.


        k: int

        Highest ranked k entities.

        Returns: Tuple
        ---------

        Highest K scores and entities
        """

        head_entity = torch.LongTensor([self.entity_to_idx[i] for i in head_entity])
        relation = torch.arange(0, len(self.relation_to_idx))
        tail_entity = torch.LongTensor([self.entity_to_idx[i] for i in tail_entity])

        x = torch.stack((head_entity.repeat(self.num_relations, ),
                         relation,
                         tail_entity.repeat(self.num_relations, )), dim=1)
        return self.model(x)
        # scores = self.model(x)
        # sort_scores, sort_idxs = torch.topk(scores, topk)
        # return sort_scores, [self.idx_to_relations[i] for i in sort_idxs.tolist()]

    def predict_missing_tail_entity(self, head_entity: List[str], relation: List[str]) -> torch.FloatTensor:
        """
        Given a head entity and a relation, return top k ranked entities

        argmax_{e \in E } f(h,r,e), where h \in E and r \in R.


        Parameter
        ---------
        head_entity: List[str]

        String representation of selected entities.

        tail_entity: List[str]

        String representation of selected entities.

        Returns: Tuple
        ---------

        scores
        """
        x = torch.cat((torch.LongTensor([self.entity_to_idx[i] for i in head_entity]).unsqueeze(-1),
                       torch.LongTensor([self.relation_to_idx[i] for i in relation]).unsqueeze(-1)), dim=1)
        return self.model.forward(x)

    def predict(self, *, h: List[str] = None, r: List[str] = None, t: List[str] = None):
        # (1) Sanity checking.
        if h is not None:
            assert isinstance(h, list)
            assert isinstance(h[0], str)
        if r is not None:
            assert isinstance(r, list)
            assert isinstance(r[0], str)
        if t is not None:
            assert isinstance(t, list)
            assert isinstance(t[0], str)
        # (2) Predict missing head entity given a relation and a tail entity.
        if h is None:
            assert r is not None
            assert t is not None
            # ? r, t
            scores = self.predict_missing_head_entity(r, t)
        # (3) Predict missing relation given a head entity and a tail entity.
        elif r is None:
            assert h is not None
            assert t is not None
            # h ? t
            scores = self.predict_missing_relations(h, t)
        # (4) Predict missing tail entity given a head entity and a relation
        elif t is None:
            assert h is not None
            assert r is not None
            # h r ?
            scores = self.predict_missing_tail_entity(h, r)
        else:
            assert len(h) == len(r) == len(t)
            scores = self.triple_score(h, r, t)
        return torch.sigmoid(scores)

    def predict_topk(self, *, h: List[str] = None, r: List[str] = None, t: List[str] = None,
                     topk: int = 10):
        """
        Predict missing item in a given triple.



        Parameter
        ---------
        head_entity: List[str]

        String representation of selected entities.

        relation: List[str]

        String representation of selected relations.

        tail_entity: List[str]

        String representation of selected entities.


        k: int

        Highest ranked k item.

        Returns: Tuple
        ---------

        Highest K scores and items
        """

        # (1) Sanity checking.
        if h is not None:
            assert isinstance(h, list)
        if r is not None:
            assert isinstance(r, list)
        if t is not None:
            assert isinstance(t, list)
        # (2) Predict missing head entity given a relation and a tail entity.
        if h is None:
            assert r is not None
            assert t is not None
            # ? r, t
            scores = self.predict_missing_head_entity(r, t).flatten()
            if self.apply_semantic_constraint:
                # filter the scores
                for th, i in enumerate(r):
                    scores[self.domain_constraints_per_rel[self.relation_to_idx[i]]] = -torch.inf

            sort_scores, sort_idxs = torch.topk(scores, topk)
            return torch.sigmoid(sort_scores), [self.idx_to_entity[i] for i in sort_idxs.tolist()]
        # (3) Predict missing relation given a head entity and a tail entity.
        elif r is None:
            assert h is not None
            assert t is not None
            # h ? t
            scores = self.predict_missing_relations(h, t).flatten()
            sort_scores, sort_idxs = torch.topk(scores, topk)
            return torch.sigmoid(sort_scores), [self.idx_to_relations[i] for i in sort_idxs.tolist()]
        # (4) Predict missing tail entity given a head entity and a relation
        elif t is None:
            assert h is not None
            assert r is not None
            # h r ?t
            scores = self.predict_missing_tail_entity(h, r).flatten()
            if self.apply_semantic_constraint:
                # filter the scores
                for th, i in enumerate(r):
                    scores[self.range_constraints_per_rel[self.relation_to_idx[i]]] = -torch.inf
            sort_scores, sort_idxs = torch.topk(scores, topk)
            return torch.sigmoid(sort_scores), [self.idx_to_entity[i] for i in sort_idxs.tolist()]
        else:
            raise AttributeError('Use triple_score method')

    def triple_score(self, h: List[str] = None, r: List[str] = None,
                     t: List[str] = None, logits=False) -> torch.FloatTensor:
        """
        Predict triple score

        Parameter
        ---------
        head_entity: List[str]

        String representation of selected entities.

        relation: List[str]

        String representation of selected relations.

        tail_entity: List[str]

        String representation of selected entities.

        logits: bool

        If logits is True, unnormalized score returned

        Returns: Tuple
        ---------

        pytorch tensor of triple score
        """
        h = torch.LongTensor([self.entity_to_idx[i] for i in h]).reshape(len(h), 1)
        r = torch.LongTensor([self.relation_to_idx[i] for i in r]).reshape(len(r), 1)
        t = torch.LongTensor([self.entity_to_idx[i] for i in t]).reshape(len(t), 1)

        x = torch.hstack((h, r, t))
        if self.apply_semantic_constraint:
            raise NotImplementedError()
        else:
            with torch.no_grad():
                out = self.model(x)
                if logits:
                    return out
                else:
                    return torch.sigmoid(out)

    def predict_conjunctive_query(self, entity: str, relations: List[str], topk: int = 3,
                                  show_intermediate_results=False) -> Set[str]:
        """
         Find an answer set for a conjunctive query.

         A graphical explanation is shown below
                                                    -> result_1
                                -> e_i,relations[1] -> result_2
                                                    -> result_3

                                                    -> result_4
         entity, relations[0]   -> e_j,relations[1] -> result_5
                                                    -> result_7

                                                    -> result_8
                                -> e_k,relations[1] -> result_9
                                                    -> result_10

        Parameter
        ---------
        entity: str

        String representation of a selected/anchor entity.

        relations: List[str]

        String representations of selected relations.

        topk: int

        Highest ranked k item.

        Returns: Tuple
        ---------

        Highest K scores and entities
        """

        assert isinstance(entity, str)
        assert isinstance(relations, list)
        assert len(entity) >= 1
        assert len(relations) >= 1
        # (1) An entity set.
        results = set()
        # (2) Bookkeeping.
        each_intermediate_result = dict()
        hop_counter = 0
        # (3) Iterate over each relation.
        for r in relations:
            # (3.1) if entity is an anchor entity:
            if len(results) == 0:
                top_ranked_entities = self.predict_topk(h=[entity], r=[r], topk=topk)[1]
                results = set(top_ranked_entities)
                each_intermediate_result[(hop_counter, entity, r)] = top_ranked_entities
            else:
                # (3.2) Iterative over intermediate results
                temp_intermediate_results = set()
                while results:
                    entity = results.pop()
                    top_ranked_entities = self.predict_topk(h=[entity], r=[r], topk=topk)[1]
                    temp_intermediate_results |= set(top_ranked_entities)
                    each_intermediate_result[(hop_counter, entity, r)] = top_ranked_entities
                # (3.3)
                results = temp_intermediate_results
            hop_counter += 1
        if show_intermediate_results is True:
            return results, each_intermediate_result
        else:
            return results

    def t_norm(self, tens_1: torch.Tensor, tens_2: torch.Tensor, tnorm: str = 'min') -> torch.Tensor:
        if 'min' in tnorm:
            return torch.min(tens_1, tens_2)
        elif 'prod' in tnorm:
            return tens_1 * tens_2

    def t_conorm(self, tens_1: torch.Tensor, tens_2: torch.Tensor, tconorm: str = 'min') -> torch.Tensor:
        if 'min' in tconorm:
            return torch.max(tens_1, tens_2)
        elif 'prod' in tconorm:
            return (tens_1 + tens_2) - (tens_1 * tens_2)

    def negnorm(self, tens_1: torch.Tensor, lambda_: float, neg_norm: str = 'standard') -> torch.Tensor:
        if 'standard' in neg_norm:
            return 1 - tens_1
        elif 'sugeno' in neg_norm:
            return (1 - tens_1) / (1 + lambda_ * tens_1)
        elif 'yager' in neg_norm:
            return (1 - torch.pow(tens_1, lambda_)) ** (1 / lambda_)

    def answer_multi_hop_query(self, query_type: str, query: Tuple[Union[str, Tuple[str, str]], ...], tnorm: str="prod",
                               neg_norm: str="standard", lambda_: float=0.0, k: int=10,only_scores=False) -> List[Tuple[str, torch.Tensor]]:
        """
        Find an answer set for EPFO queries including negation and disjunction

        Parameter
        ----------
        query_type: str
        The type of the query, e.g., "2p".

        query: Union[str, Tuple[str, Tuple[str, str]]]
        The query itself, either a string or a nested tuple.

        tnorm: str
        The t-norm operator.

        neg_norm: str
        The negation norm.

        lambda_: float
        lambda parameter for sugeno and yager negation norms

        k: int
        The top-k substitutions for intermediate variables.

        Returns
        -------
        List[Tuple[str, torch.Tensor]]
        Entities and corresponding scores sorted in the descening order of scores
        """
        assert len(self.entity_to_idx) > k >= 0

        query_name_dict = {
            ("e", ("r",)): "1p",
            ("e", ("r", "r")): "2p",
            ("e", ("r", "r", "r",),): "3p",
            (("e", ("r",)), ("e", ("r",))): "2i",
            (("e", ("r",)), ("e", ("r",)), ("e", ("r",))): "3i",
            ((("e", ("r",)), ("e", ("r",))), ("r",)): "ip",
            (("e", ("r", "r")), ("e", ("r",))): "pi",
            # negation
            (("e", ("r",)), ("e", ("r", "n"))): "2in",
            (("e", ("r",)), ("e", ("r",)), ("e", ("r", "n"))): "3in",
            ((("e", ("r",)), ("e", ("r", "n"))), ("r",)): "inp",
            (("e", ("r", "r")), ("e", ("r", "n"))): "pin",
            (("e", ("r", "r", "n")), ("e", ("r",))): "pni",

            # union
            (("e", ("r",)), ("e", ("r",)), ("u",)): "2u",
            ((("e", ("r",)), ("e", ("r",)), ("u",)), ("r",)): "up",

        }

        # Create an inverse mapping
        inverse_query_name_dict = {v: k for k, v in query_name_dict.items()}

        # Look up the corresponding query_structure
        if query_type in inverse_query_name_dict:
            query_structure = inverse_query_name_dict[query_type]
        else:
            raise ValueError(f"Invalid query type: {query_type}")
        #2in
        if query_structure == (("e", ("r",)), ("e", ("r", "n"))):
            # entity_scores = scores_2in(query, tnorm, neg_norm, lambda_)
            head1, relation1 = query[0]
            head2, relation2 = query[1]

            # Calculate entity scores for each query
            # Get scores for the first atom (positive)
            atom1_scores = self.predict(h=[head1], r=[relation1[0]]).squeeze()
            # Get scores for the second atom (negative)
            # if neg_norm == "standard":
            predictions = self.predict(h=[head2], r=[relation2[0]]).squeeze()
            atom2_scores = self.negnorm(predictions, lambda_, neg_norm)

            assert len(atom1_scores) == len(self.entity_to_idx)

            combined_scores = self.t_norm(atom1_scores, atom2_scores, tnorm)
            if only_scores:
                return combined_scores
            entity_scores = [(ei, s) for ei, s in zip(self.entity_to_idx.keys(), combined_scores)]
            return sorted(entity_scores, key=lambda x: x[1], reverse=True)
        # 3in
        elif query_structure == (("e", ("r",)), ("e", ("r",)), ("e", ("r", "n"))):
            # entity_scores = scores_3in(model, query, tnorm, neg_norm, lambda_)
            head1, relation1 = query[0]
            head2, relation2 = query[1]
            head3, relation3 = query[2]

            # Calculate entity scores for each query
            # Get scores for the first atom (positive)
            atom1_scores = self.predict(h=[head1], r=[relation1[0]]).squeeze()
            # Get scores for the second atom (negative)
            # modelling standard negation (1-x)
            atom2_scores = self.predict(h=[head2], r=[relation2[0]]).squeeze()
            # Get scores for the third atom
            # if neg_norm == "standard":
            predictions = self.predict(h=[head3], r=[relation3[0]]).squeeze()
            atom3_scores = self.negnorm(predictions, lambda_, neg_norm)

            assert len(atom1_scores) == len(self.entity_to_idx)

            inter_scores = self.t_norm(atom1_scores, atom2_scores, tnorm)
            combined_scores = self.t_norm(inter_scores, atom3_scores, tnorm)
            if only_scores:
                return combined_scores
            entity_scores = [(ei, s) for ei, s in zip(self.entity_to_idx.keys(), combined_scores)]
            return sorted(entity_scores, key=lambda x: x[1], reverse=True)
        # pni
        elif query_structure == (("e", ("r", "r", "n")), ("e", ("r",))):
            # entity_scores = scores_pni(model, query, tnorm, neg_norm, lambda_, k_)
            head1, (relation1, relation2, _) = query[0]
            head3, relation3 = query[1]
            # Calculate entity scores for each query
            # Get scores for the first atom
            atom1_scores = self.predict(h=[head1], r=[relation1]).squeeze()

            assert len(atom1_scores) == len(self.entity_to_idx)
            # sort atom1_scores in descending order and get the top k entities indices
            top_k_scores1, top_k_indices = torch.topk(atom1_scores, k)

            # using model.entity_to_idx.keys() take the name of entities from topk heads 2
            entity_to_idx_keys = list(self.entity_to_idx.keys())
            top_k_heads = [entity_to_idx_keys[idx.item()] for idx in top_k_indices]

            # Get scores for the second atom
            # Initialize an empty tensor
            atom2_scores = torch.empty(0, len(self.entity_to_idx)).to(atom1_scores.device)

            # Get scores for the second atom
            for head2 in top_k_heads:
                # The score tensor for the current head2
                atom2_score = self.predict(h=[head2], r=[relation2])
                neg_atom2_score = self.negnorm(atom2_score, lambda_, neg_norm)
                # Concatenate the score tensor for the current head2 with the previous scores
                atom2_scores = torch.cat([atom2_scores, neg_atom2_score], dim=0)

            topk_scores1_expanded = top_k_scores1.view(-1, 1).repeat(1, atom2_scores.shape[1])

            inter_scores = self.t_norm(topk_scores1_expanded, atom2_scores, tnorm)

            scores_2pn_query, _ = torch.max(inter_scores, dim=0)
            scores_1p_query = self.predict(h=[head3], r=[relation3[0]]).squeeze()

            combined_scores = self.t_norm(scores_2pn_query, scores_1p_query, tnorm)
            if only_scores:
                return combined_scores
            entity_scores = [(ei, s) for ei, s in zip(self.entity_to_idx.keys(), combined_scores)]
            return sorted(entity_scores, key=lambda x: x[1], reverse=True)
        # pin
        elif query_structure == (("e", ("r", "r")), ("e", ("r", "n"))):
            # entity_scores = scores_pin(model, query, tnorm, neg_norm, lambda_, k_)
            head1, (relation1, relation2) = query[0]
            head3, relation3 = query[1]
            # Calculate entity scores for each query
            # Get scores for the first atom
            atom1_scores = self.predict(h=[head1], r=[relation1]).squeeze()

            assert len(atom1_scores) == len(self.entity_to_idx)

            # sort atom1_scores in descending order and get the top k entities indices
            top_k_scores1, top_k_indices = torch.topk(atom1_scores, k)

            # using model.entity_to_idx.keys() take the name of entities from topk heads 2
            entity_to_idx_keys = list(self.entity_to_idx.keys())
            top_k_heads = [entity_to_idx_keys[idx.item()] for idx in top_k_indices]

            # Initialize an empty tensor
            atom2_scores = torch.empty(0, len(self.entity_to_idx)).to(atom1_scores.device)

            # Get scores for the second atom
            for head2 in top_k_heads:
                # The score tensor for the current head2
                atom2_score = self.predict(h=[head2], r=[relation2])
                # Concatenate the score tensor for the current head2 with the previous scores
                atom2_scores = torch.cat([atom2_scores, atom2_score], dim=0)

            topk_scores1_expanded = top_k_scores1.view(-1, 1).repeat(1, atom2_scores.shape[1])

            inter_scores = self.t_norm(topk_scores1_expanded, atom2_scores, tnorm)

            scores_2p_query, _ = torch.max(inter_scores, dim=0)

            scores_1p_query = self.predict(h=[head3], r=[relation3[0]]).squeeze()
            # taking negation for the e,(r,n) part of query
            neg_scores_1p_query = self.negnorm(scores_1p_query, lambda_, neg_norm)
            combined_scores = self.t_norm(scores_2p_query, neg_scores_1p_query, tnorm)
            if only_scores:
                return combined_scores
            entity_scores = [(ei, s) for ei, s in zip(self.entity_to_idx.keys(), combined_scores)]
            return sorted(entity_scores, key=lambda x: x[1], reverse=True)
        # inp
        elif query_structure == ((("e", ("r",)), ("e", ("r", "n"))), ("r",)):
            # entity_scores = scores_inp(model, query, tnorm, neg_norm, lambda_, k_)
            head1, relation1 = query[0][0]
            head2, relation2 = query[0][1]
            relation_1p = query[1]

            # Calculate entity scores for each query
            # Get scores for the first atom (positive)
            atom1_scores = self.predict(h=[head1], r=[relation1[0]]).squeeze()
            # Get scores for the second atom (negative)
            # if neg_norm == "standard":
            predictions = self.predict(h=[head2], r=[relation2[0]]).squeeze()
            atom2_scores = self.negnorm(predictions, lambda_, neg_norm)

            assert len(atom1_scores) == len(self.entity_to_idx)

            scores_2in_query = self.t_norm(atom1_scores, atom2_scores, tnorm)

            # sort atom1_scores in descending order and get the top k entities indices
            top_k_scores1, top_k_indices = torch.topk(scores_2in_query, k)

            # using model.entity_to_idx.keys() take the name of entities from topk heads 2
            entity_to_idx_keys = list(self.entity_to_idx.keys())
            top_k_heads = [entity_to_idx_keys[idx.item()] for idx in top_k_indices]

            # Get scores for the second atom
            # Initialize an empty tensor
            atom3_scores = torch.empty(0, len(self.entity_to_idx)).to(scores_2in_query.device)

            # Get scores for the second atom
            for head3 in top_k_heads:
                # The score tensor for the current head2
                atom3_score = self.predict(h=[head3], r=[relation_1p[0]])
                # Concatenate the score tensor for the current head2 with the previous scores
                atom3_scores = torch.cat([atom3_scores, atom3_score], dim=0)

            topk_scores1_expanded = top_k_scores1.view(-1, 1).repeat(1, atom3_scores.shape[1])

            combined_scores = self.t_norm(topk_scores1_expanded, atom3_scores, tnorm)

            res, _ = torch.max(combined_scores, dim=0)
            if only_scores:
                return res
            entity_scores = [(ei, s) for ei, s in zip(self.entity_to_idx.keys(), res)]
            return sorted(entity_scores, key=lambda x: x[1], reverse=True)
        # 1p
        elif query_structure == ("e", ("r",)):
            head1, relation1 = query
            # Calculate entity scores for each query
            # Get scores for the first atom
            atom1_scores = self.predict(h=[head1], r=[relation1[0]]).squeeze()
            if only_scores:
                return atom1_scores
            entity_scores = [(ei, s) for ei, s in zip(self.entity_to_idx.keys(), atom1_scores)]
            return sorted(entity_scores, key=lambda x: x[1], reverse=True)

        # 2p
        elif query_structure == ("e", ("r", "r")):
            # entity_scores = scores_2p(model, query, tnorm, k_)
            head1, (relation1, relation2) = query

            # Calculate entity scores for each query
            # Get scores for the first atom
            atom1_scores = self.predict(h=[head1], r=[relation1]).squeeze()

            assert len(atom1_scores) == len(self.entity_to_idx)
            # sort atom1_scores in descending order and get the top k entities indices
            top_k_scores1, top_k_indices = torch.topk(atom1_scores, k)

            # using model.entity_to_idx.keys() take the name of entities from topk heads 2
            entity_to_idx_keys = list(self.entity_to_idx.keys())
            top_k_heads = [entity_to_idx_keys[idx.item()] for idx in top_k_indices]

            # Initialize an empty tensor
            atom2_scores = torch.empty(0, len(self.entity_to_idx)).to(atom1_scores.device)

            # Get scores for the second atom
            for head2 in top_k_heads:
                # The score tensor for the current head2
                atom2_score = self.predict(h=[head2], r=[relation2])
                # Concatenate the score tensor for the current head2 with the previous scores
                atom2_scores = torch.cat([atom2_scores, atom2_score], dim=0)

            topk_scores1_expanded = top_k_scores1.view(-1, 1).repeat(1, atom2_scores.shape[1])

            combined_scores = self.t_norm(topk_scores1_expanded, atom2_scores, tnorm)
            res, _ = torch.max(combined_scores, dim=0)
            if only_scores:
                return res
            entity_scores = [(ei, s) for ei, s in zip(self.entity_to_idx.keys(), res)]
            return sorted(entity_scores, key=lambda x: x[1], reverse=True)

        # 3p
        elif query_structure == ("e", ("r", "r", "r",)):
            head1, (relation1, relation2, relation3) = query

            # Get scores for the first atom
            atom1_scores = self.predict(h=[head1], r=[relation1]).squeeze()
            # Get the top k entities indices for the first atom
            top_k_scores1, top_k_indices1 = torch.topk(atom1_scores, k)

            # Get the name of entities from top k heads for the first atom
            entity_to_idx_keys = list(self.entity_to_idx.keys())
            top_k_heads1 = [entity_to_idx_keys[idx.item()] for idx in top_k_indices1]

            # Initialize an empty tensor for the second atom scores
            atom2_scores = torch.empty(0, len(self.entity_to_idx)).to(atom1_scores.device)

            # Get scores for the second atom
            for head2 in top_k_heads1:
                atom2_score = self.predict(h=[head2], r=[relation2])
                atom2_scores = torch.cat([atom2_scores, atom2_score], dim=0)

            # Get the top k entities indices for each head of the second atom
            top_k_scores2, top_k_indices2 = torch.topk(atom2_scores, k, dim=1)

            # Get the name of entities from top k heads for each head of the second atom
            top_k_heads2 = [[entity_to_idx_keys[idx.item()] for idx in row] for row in top_k_indices2]

            # Initialize an empty tensor for the third atom scores
            atom3_scores = torch.empty(0, len(self.entity_to_idx)).to(atom1_scores.device)

            # Get scores for the third atom
            for row in top_k_heads2:
                for head3 in row:
                    atom3_score = self.predict(h=[head3], r=[relation3])
                    atom3_scores = torch.cat([atom3_scores, atom3_score], dim=0)

            topk_scores1_2d = top_k_scores1.unsqueeze(-1).repeat(1, top_k_scores2.shape[1])
            topk_scores1_expanded = topk_scores1_2d.view(-1, 1).repeat(1, atom3_scores.shape[1])
            topk_scores2_expanded = top_k_scores2.view(-1, 1).repeat(1, atom3_scores.shape[1])

            inter_scores = self.t_norm(topk_scores1_expanded, topk_scores2_expanded, tnorm)
            # atom3_scores_flattened = atom3_scores.view(-1)

            combined_scores = self.t_norm(inter_scores, atom3_scores, tnorm)
            res, _ = torch.max(combined_scores, dim=0)
            if only_scores:
                return res
            entity_scores = [(ei, s) for ei, s in zip(self.entity_to_idx.keys(), res)]
            return sorted(entity_scores, key=lambda x: x[1], reverse=True)
        # 2i
        elif query_structure == (("e", ("r",)), ("e", ("r",))):
            # entity_scores = scores_2i(model, query, tnorm)
            head1, relation1 = query[0]
            head2, relation2 = query[1]

            # Calculate entity scores for each query
            # Get scores for the first atom
            atom1_scores = self.predict(h=[head1], r=[relation1[0]]).squeeze()
            # Get scores for the second atom
            atom2_scores = self.predict(h=[head2], r=[relation2[0]]).squeeze()

            assert len(atom1_scores) == len(self.entity_to_idx)

            combined_scores = self.t_norm(atom1_scores, atom2_scores, tnorm)
            if only_scores:
                return combined_scores
            entity_scores = [(ei, s) for ei, s in zip(self.entity_to_idx.keys(), combined_scores)]
            return sorted(entity_scores, key=lambda x: x[1], reverse=True)
        # 3i
        elif query_structure == (("e", ("r",)), ("e", ("r",)), ("e", ("r",))):
            # entity_scores = scores_3i(model, query, tnorm)
            head1, relation1 = query[0]
            head2, relation2 = query[1]
            head3, relation3 = query[2]
            # Calculate entity scores for each query
            # Get scores for the first atom
            atom1_scores = self.predict(h=[head1], r=[relation1[0]]).squeeze()
            # Get scores for the second atom
            atom2_scores = self.predict(h=[head2], r=[relation2[0]]).squeeze()
            # Get scores for the third atom
            atom3_scores = self.predict(h=[head3], r=[relation3[0]]).squeeze()

            assert len(atom1_scores) == len(self.entity_to_idx)

            inter_scores = self.t_norm(atom1_scores, atom2_scores, tnorm)
            combined_scores = self.t_norm(inter_scores, atom3_scores, tnorm)
            if only_scores:
                return combined_scores
            entity_scores = [(ei, s) for ei, s in zip(self.entity_to_idx.keys(), combined_scores)]
            return sorted(entity_scores, key=lambda x: x[1], reverse=True)
        # pi
        elif query_structure == (("e", ("r", "r")), ("e", ("r",))):
            # entity_scores = scores_pi(model, query, tnorm, k_)
            head1, (relation1, relation2) = query[0]
            head3, relation3 = query[1]
            # Calculate entity scores for each query
            # Get scores for the first atom
            atom1_scores = self.predict(h=[head1], r=[relation1]).squeeze()

            assert len(atom1_scores) == len(self.entity_to_idx)
            # sort atom1_scores in descending order and get the top k entities indices
            top_k_scores1, top_k_indices = torch.topk(atom1_scores, k)

            # using model.entity_to_idx.keys() take the name of entities from topk heads 2
            entity_to_idx_keys = list(self.entity_to_idx.keys())
            top_k_heads = [entity_to_idx_keys[idx.item()] for idx in top_k_indices]

            # Initialize an empty tensor
            atom2_scores = torch.empty(0, len(self.entity_to_idx)).to(atom1_scores.device)

            # Get scores for the second atom
            for head2 in top_k_heads:
                # The score tensor for the current head2
                atom2_score = self.predict(h=[head2], r=[relation2])
                # Concatenate the score tensor for the current head2 with the previous scores
                atom2_scores = torch.cat([atom2_scores, atom2_score], dim=0)

            topk_scores1_expanded = top_k_scores1.view(-1, 1).repeat(1, atom2_scores.shape[1])

            inter_scores = self.t_norm(topk_scores1_expanded, atom2_scores, tnorm)

            scores_2p_query, _ = torch.max(inter_scores, dim=0)

            scores_1p_query = self.predict(h=[head3], r=[relation3[0]]).squeeze()

            combined_scores = self.t_norm(scores_2p_query, scores_1p_query, tnorm)
            if only_scores:
                return combined_scores
            entity_scores = [(ei, s) for ei, s in zip(self.entity_to_idx.keys(), combined_scores)]
            return sorted(entity_scores, key=lambda x: x[1], reverse=True)
        # ip
        elif query_structure == ((("e", ("r",)), ("e", ("r",))), ("r",)):
            # entity_scores = scores_ip(model, query, tnorm, k_)
            head1, relation1 = query[0][0]
            head2, relation2 = query[0][1]
            relation_1p = query[1]
            # Calculate entity scores for each query
            # Get scores for the first atom
            atom1_scores = self.predict(h=[head1], r=[relation1[0]]).squeeze()
            # Get scores for the second atom
            atom2_scores = self.predict(h=[head2], r=[relation2[0]]).squeeze()

            assert len(atom1_scores) == len(self.entity_to_idx)

            scores_2i_query = self.t_norm(atom1_scores, atom2_scores, tnorm)
            # Get the top k entities from the 2i query

            # sort atom1_scores in descending order and get the top k entities indices
            top_k_scores1, top_k_indices = torch.topk(scores_2i_query, k)

            # using model.entity_to_idx.keys() take the name of entities from topk heads
            entity_to_idx_keys = list(self.entity_to_idx.keys())
            top_k_heads = [entity_to_idx_keys[idx.item()] for idx in top_k_indices]

            # Get scores for the second atom
            # Initialize an empty tensor
            atom3_scores = torch.empty(0, len(self.entity_to_idx)).to(scores_2i_query.device)

            # Get scores for the second atom
            for head3 in top_k_heads:
                # The score tensor for the current head2
                atom3_score = self.predict(h=[head3], r=[relation_1p[0]])
                # Concatenate the score tensor for the current head2 with the previous scores
                atom3_scores = torch.cat([atom3_scores, atom3_score], dim=0)

            topk_scores1_expanded = top_k_scores1.view(-1, 1).repeat(1, atom3_scores.shape[1])

            combined_scores = self.t_norm(topk_scores1_expanded, atom3_scores, tnorm)
            res, _ = torch.max(combined_scores, dim=0)
            if only_scores:
                return res
            entity_scores = [(ei, s) for ei, s in zip(self.entity_to_idx.keys(), res)]
            return sorted(entity_scores, key=lambda x: x[1], reverse=True)
        # disjunction
        # 2u
        elif query_structure == (("e", ("r",)), ("e", ("r",)), ("u",)):
            # entity_scores = scores_2u(model, query, tnorm)
            head1, relation1 = query[0]
            head2, relation2 = query[1]

            # Calculate entity scores for each query
            # Get scores for the first atom
            atom1_scores = self.predict(h=[head1], r=[relation1[0]]).squeeze()
            # Get scores for the second atom
            atom2_scores = self.predict(h=[head2], r=[relation2[0]]).squeeze()

            assert len(atom1_scores) == len(self.entity_to_idx)

            combined_scores = self.t_conorm(atom1_scores, atom2_scores, tnorm)
            if only_scores:
                return combined_scores
            entity_scores = [(ei, s) for ei, s in zip(self.entity_to_idx.keys(), combined_scores)]
            entity_scores = sorted(entity_scores, key=lambda x: x[1], reverse=True)

            return entity_scores
        # up
        # here the second tnorm is for t-conorm (used in pairs)
        elif query_structure == ((("e", ("r",)), ("e", ("r",)), ("u",)), ("r",)):
            # entity_scores = scores_up(model, query, tnorm, tnorm, k_)
            head1, relation1 = query[0][0]
            head2, relation2 = query[0][1]
            relation_1p = query[1]

            # Get scores for the first atom
            atom1_scores = self.predict(h=[head1], r=[relation1[0]]).squeeze()

            # Get scores for the second atom
            atom2_scores = self.predict(h=[head2], r=[relation2[0]]).squeeze()

            assert len(atom1_scores) == len(self.entity_to_idx)

            scores_2u_query = self.t_conorm(atom1_scores, atom2_scores, tnorm)

            # Sort atom1_scores in descending order and get the top k entities indices
            top_k_scores1, top_k_indices = torch.topk(scores_2u_query, k)

            # Using model.entity_to_idx.keys() take the name of entities from topk heads
            entity_to_idx_keys = list(self.entity_to_idx.keys())
            top_k_heads = [entity_to_idx_keys[idx.item()] for idx in top_k_indices]

            # Initialize an empty tensor
            atom3_scores = torch.empty(0, len(self.entity_to_idx)).to(scores_2u_query.device)

            for head3 in top_k_heads:
                # The score tensor for the current head3
                atom3_score = self.predict(h=[head3], r=[relation_1p[0]])

                # Concatenate the score tensor for the current head3 with the previous scores
                atom3_scores = torch.cat([atom3_scores, atom3_score], dim=0)

            topk_scores1_expanded = top_k_scores1.view(-1, 1).repeat(1, atom3_scores.shape[1])
            combined_scores = self.t_norm(topk_scores1_expanded, atom3_scores, tnorm)
            res, _ = torch.max(combined_scores, dim=0)
            if only_scores:
                return res
            entity_scores = [(ei, s) for ei, s in zip(self.entity_to_idx.keys(), res)]
            return  sorted(entity_scores, key=lambda x: x[1], reverse=True)
        else:
            raise RuntimeError(f"Incorrect query_structure {query_structure}")

    def find_missing_triples(self, confidence: float, entities: List[str] = None, relations: List[str] = None,
                             topk: int = 10,
                             at_most: int = sys.maxsize) -> Set:
        """
         Find missing triples

         Iterative over a set of entities E and a set of relation R : \forall e \in E and \forall r \in R f(e,r,x)
         Return (e,r,x)\not\in G and  f(e,r,x) > confidence

        Parameter
        ---------
        confidence: float

        A threshold for an output of a sigmoid function given a triple.

        topk: int

        Highest ranked k item to select triples with f(e,r,x) > confidence .

        at_most: int

        Stop after finding at_most missing triples

        Returns: Set
        ---------

        {(e,r,x) | f(e,r,x) > confidence \land (e,r,x) \not\in G
        """

        assert 1.0 >= confidence >= 0.0
        assert topk >= 1

        def select(items: List[str], item_mapping: Dict[str, int]) -> Iterable[Tuple[str, int]]:
            """
             Get selected entities and their indexes

            Parameter
            ---------
            items: list

            item_mapping: dict


            Returns: Iterable
            ---------

            """

            if items is None:
                return item_mapping.items()
            else:
                return ((i, item_mapping[i]) for i in items)

        extended_triples = set()
        print(f'Number of entities:{len(self.entity_to_idx)} \t Number of relations:{len(self.relation_to_idx)}')

        # (5) Cartesian Product over entities and relations
        # (5.1) Iterate over entities
        print('Finding missing triples..')
        for str_head_entity, idx_entity in select(entities, self.entity_to_idx):
            # (5.1) Iterate over relations
            for str_relation, idx_relation in select(relations, self.relation_to_idx):
                # (5.2) \forall e \in Entities store a tuple of scoring_func(head,relation,e) and e
                # (5.3.) Sort (5.2) and return top  tuples
                predicted_scores, str_tail_entities = self.predict_topk(h=[str_head_entity],
                                                                        r=[str_relation], topk=topk)
                # (5.4) Iterate over 5.3
                for predicted_score, str_entity in zip(predicted_scores, str_tail_entities):
                    # (5.5) If score is less than 99% ignore it
                    if predicted_score < confidence:
                        break
                    else:
                        # (5.8) Remember it
                        extended_triples.add((str_head_entity, str_relation, str_entity))
                        print(f'Number of found missing triples: {len(extended_triples)}')
                        if len(extended_triples) == at_most:
                            return extended_triples
                        # No need to store a large KG into memory
                        # /5.6) False if 0, otherwise 1
                        is_in = np.any(
                            np.all(self.train_set == [idx_entity, idx_relation, self.entity_to_idx[str_entity]],
                                   axis=1))
                        # (5.7) If (5.6) is true, ignore it
                        if is_in:
                            continue
                        else:
                            # (5.8) Remember it
                            extended_triples.add((str_head_entity, str_relation, str_entity))
                            print(f'Number of found missing triples: {len(extended_triples)}')
                            if len(extended_triples) == at_most:
                                return extended_triples
        return extended_triples

    def deploy(self, share: bool = False, top_k: int = 10):
        import gradio as gr

        def predict(str_subject: str, str_predicate: str, str_object: str, random_examples: bool):
            if random_examples:
                return random_prediction(self)
            else:
                if self.is_seen(entity=str_subject) and self.is_seen(
                        relation=str_predicate) and self.is_seen(entity=str_object):
                    """ Triple Prediction """
                    return deploy_triple_prediction(self, str_subject, str_predicate, str_object)

                elif self.is_seen(entity=str_subject) and self.is_seen(
                        relation=str_predicate):
                    """ Tail Entity Prediction """
                    return deploy_tail_entity_prediction(self, str_subject, str_predicate, top_k)
                elif self.is_seen(entity=str_object) and self.is_seen(
                        relation=str_predicate):
                    """ Head Entity Prediction """
                    return deploy_head_entity_prediction(self, str_object, str_predicate, top_k)
                elif self.is_seen(entity=str_subject) and self.is_seen(entity=str_object):
                    """ Relation Prediction """
                    return deploy_relation_prediction(self, str_subject, str_object, top_k)
                else:
                    KeyError('Uncovered scenario')
            # If user simply select submit
            return random_prediction(self)

        gr.Interface(
            fn=predict,
            inputs=[gr.inputs.Textbox(lines=1, placeholder=None, label='Subject'),
                    gr.inputs.Textbox(lines=1, placeholder=None, label='Predicate'),
                    gr.inputs.Textbox(lines=1, placeholder=None, label='Object'), "checkbox"],
            outputs=[gr.outputs.Textbox(label='Input Triple'),
                     gr.outputs.Dataframe(label='Outputs', type='pandas')],
            title=f'{self.name} Deployment',
            description='1. Enter a triple to compute its score,\n'
                        '2. Enter a subject and predicate pair to obtain most likely top ten entities or\n'
                        '3. Checked the random examples box and click submit').launch(share=share)

    # @TODO: Do we really need this ?!
    def train_triples(self, h: List[str], r: List[str], t: List[str], labels: List[float],
                      iteration=2, optimizer=None):
        assert len(h) == len(r) == len(t) == len(labels)
        # (1) From List of strings to TorchLongTensor.
        x = torch.LongTensor(self.index_triple(h, r, t)).reshape(1, 3)
        # (2) From List of float to Torch Tensor.
        labels = torch.FloatTensor(labels)
        # (3) Train mode.
        self.set_model_train_mode()
        if optimizer is None:
            optimizer = optim.Adam(self.model.parameters(), lr=0.1)
        print('Iteration starts...')
        # (4) Train.
        for epoch in range(iteration):
            optimizer.zero_grad()
            outputs = self.model(x)
            loss = self.model.loss(outputs, labels)
            print(f"Iteration:{epoch}\t Loss:{loss.item()}\t Outputs:{outputs.detach().mean()}")
            loss.backward()
            optimizer.step()
        # (5) Eval
        self.set_model_eval_mode()
        with torch.no_grad():
            outputs = self.model(x)
            loss = self.model.loss(outputs, labels)
            print(f"Eval Mode:\tLoss:{loss.item()}")

    def train_k_vs_all(self, h, r, iteration=1, lr=.001):
        """
        Train k vs all
        :param head_entity:
        :param relation:
        :param iteration:
        :param lr:
        :return:
        """
        assert len(h) == 1
        # (1) Construct input and output
        out = self.construct_input_and_output_k_vs_all(h, r)
        if out is None:
            return
        x, labels, idx_tails = out
        # (2) Train mode
        self.set_model_train_mode()
        # (3) Initialize optimizer # SGD considerably faster than ADAM.
        optimizer = optim.Adam(self.model.parameters(), lr=lr, weight_decay=.00001)

        print('\nIteration starts.')
        # (3) Iterative training.
        for epoch in range(iteration):
            optimizer.zero_grad()
            outputs = self.model(x)
            loss = self.model.loss(outputs, labels)
            if len(idx_tails) > 0:
                print(
                    f"Iteration:{epoch}\t"
                    f"Loss:{loss.item()}\t"
                    f"Avg. Logits for correct tails: {outputs[0, idx_tails].flatten().mean().detach()}")
            else:
                print(
                    f"Iteration:{epoch}\t"
                    f"Loss:{loss.item()}\t"
                    f"Avg. Logits for all negatives: {outputs[0].flatten().mean().detach()}")

            loss.backward()
            optimizer.step()
            if loss.item() < .00001:
                print(f'loss is {loss.item():.3f}. Converged !!!')
                break
        # (4) Eval mode
        self.set_model_eval_mode()
        with torch.no_grad():
            outputs = self.model(x)
            loss = self.model.loss(outputs, labels)
        print(f"Eval Mode:Loss:{loss.item():.4f}\t Outputs:{outputs[0, idx_tails].flatten().detach()}\n")

    def train(self, kg, lr=.1, epoch=10, batch_size=32, neg_sample_ratio=10, num_workers=1) -> None:
        """ Retrained a pretrain model on an input KG via negative sampling."""
        # (1) Create Negative Sampling Setting for training
        print('Creating Dataset...')
        train_set = TriplePredictionDataset(kg.train_set,
                                            num_entities=len(kg.entity_to_idx),
                                            num_relations=len(kg.relation_to_idx),
                                            neg_sample_ratio=neg_sample_ratio)
        num_data_point = len(train_set)
        print('Number of data points: ', num_data_point)
        train_dataloader = DataLoader(train_set, batch_size=batch_size,
                                      #  shuffle => to have the data reshuffled at every epoc
                                      shuffle=True, num_workers=num_workers,
                                      collate_fn=train_set.collate_fn, pin_memory=True)

        # (2) Go through valid triples + corrupted triples and compute scores.
        # Average loss per triple is stored. This will be used  to indicate whether we learned something.
        print('First Eval..')
        self.set_model_eval_mode()
        first_avg_loss_per_triple = 0
        for x, y in train_dataloader:
            pred = self.model(x)
            first_avg_loss_per_triple += self.model.loss(pred, y)
        first_avg_loss_per_triple /= num_data_point
        print(first_avg_loss_per_triple)
        # (3) Prepare Model for Training
        self.set_model_train_mode()
        optimizer = optim.Adam(self.model.parameters(), lr=lr)
        print('Training Starts...')
        for epoch in range(epoch):  # loop over the dataset multiple times
            epoch_loss = 0
            for x, y in train_dataloader:
                # zero the parameter gradients
                optimizer.zero_grad()
                # forward + backward + optimize
                outputs = self.model(x)
                loss = self.model.loss(outputs, y)
                epoch_loss += loss.item()
                loss.backward()
                optimizer.step()
            print(f'Epoch={epoch}\t Avg. Loss per epoch: {epoch_loss / num_data_point:.3f}')
        # (5) Prepare For Saving
        self.set_model_eval_mode()
        print('Eval starts...')
        # (6) Eval model on training data to check how much an Improvement
        last_avg_loss_per_triple = 0
        for x, y in train_dataloader:
            pred = self.model(x)
            last_avg_loss_per_triple += self.model.loss(pred, y)
        last_avg_loss_per_triple /= len(train_set)
        print(f'On average Improvement: {first_avg_loss_per_triple - last_avg_loss_per_triple:.3f}')

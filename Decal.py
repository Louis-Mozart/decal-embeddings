import subprocess
import json
import pandas as pd
import os
import torch

gpu_available = torch.cuda.is_available()

device_type = 'gpu' if gpu_available else 'cpu'



class Decal_exp:

    def __init__(self, emb_dim:int , path_main:str, folder_name:str, Experiments_path:str, num_epochs:int, batch_size:int, scoring_technique:str,path_dataset:str):

        '''Inputs: 
           em_dim: embedding dimension
           path_main: path to the main.py file
           folder_name: name of the folder that will contain the experimentions
           Experiments_path: path were the experiments will be saved.'''

        self.path_main = path_main
        self.Experiments_path = Experiments_path
        self.folder_name = folder_name
        self.num_epochs = num_epochs
        self.batch_size = batch_size
        self.path_folder_dataset = path_dataset
        self.emb_dim = emb_dim
        self.results = dict()
        self.scoring_technique = scoring_technique
        
                    
    def run_main(self,p,q,r):

        folder_name = f"{p}_{q}_{r}"
        folder_path = os.path.join(self.folder_name, folder_name)

        subprocess.run(["python", self.path_main,"--p",str(p) ,"--q",str(q), "--r", str(r),"--storage_path",folder_path,\
                                    "--scoring_technique", self.scoring_technique, "--num_epochs", str(self.num_epochs), "--batch_size", str(self.batch_size),\
                                    "--embedding_dim", str(self.emb_dim),"--dataset_dir", self.path_folder_dataset, "--model", "DeCaL"]) 
        

    def GSDC(self, parameter_values:list) -> pd.DataFrame : #GSDC seach
        '''This function store the performance of Decal into a dataframe for all possible values of p,q,r in parameter_values.
           If not specified, parameter_values =[0,1,...,emb_dim] '''

        if parameter_values == None:
            parameter_values  = range(self.emb_dim+1)        

        for p in parameter_values:
            for q in parameter_values:
                for r in parameter_values:
                
                    if self.emb_dim%(p+q+r+1) == 0:  #divisibility criterion (1 + p + q + r should divide d)
                        
                        self.run_main(p,q,r)
                         
                            

        experiments_path = self.Experiments_path
        
        data = []

        for root, dirs, files in os.walk(experiments_path):
            dirs.sort()
            for folder in dirs:
                folder_path = os.path.join(root, folder)
                report_path = os.path.join(folder_path, 'eval_report.json')

                
                if os.path.exists(report_path):
                    with open(report_path, 'r') as file:
                        report_data = json.load(file)

                        parent_folder = os.path.basename(root)

                        data.append({
                            'Experiment': parent_folder,
                            'Train_H@1': report_data['Train']['H@1'],
                            'Train_H@3': report_data['Train']['H@3'],
                            'Train_H@10': report_data['Train']['H@10'],
                            'Train_MRR': report_data['Train']['MRR'],
                            'Val_H@1': report_data['Val']['H@1'],
                            'Val_H@3': report_data['Val']['H@3'],
                            'Val_H@10': report_data['Val']['H@10'],
                            'Val_MRR': report_data['Val']['MRR'],
                            'Test_H@1': report_data['Test']['H@1'],
                            'Test_H@3': report_data['Test']['H@3'],
                            'Test_H@10': report_data['Test']['H@10'],
                            'Test_MRR': report_data['Test']['MRR']
                        })

        df = pd.DataFrame(data)
        
        return df


    
    
    
    
    def generate_configs(self,queue, p, q, r): # generate unseen configs
        result = []
        for p_i in [-1, 0, 1]:
            for q_i in [-1, 0, 1]:
                for r_i in [-1, 0, 1]:
                    if (p+p_i, q+q_i, r+r_i) not in queue:
                        queue.append((p+p_i, q+q_i, r+r_i))
                        result.append((p+p_i, q+q_i, r+r_i))
        return result

    def score(self, queue, priority_queue):
        for (p,q,r) in queue:
            if ((p >=0) & (q >=0) & (r>=0)):
                priority_queue.append((p, q, r, self.MRR(p,q,r))) # score unseen configs
        return  priority_queue


    def GS(self, max_iterations): # Greedy seach implementation
        p, q, r = 1, 1, 1 #init
        known_configs = []
        priority_query = []
        data = []
        for i in range(0, max_iterations):
          #print(i)

            to_score = self.generate_configs(known_configs, p, q, r) # compute unseen configs

            priority_query = self.score(to_score, priority_query)	# add to priority queue, which sorts by score in descending order 
            priority_queue = sorted(priority_query,key=lambda x: x[-1], reverse=True)

            p_new,q_new,r_new,max_MRR =  priority_queue[0]  # take best config as next candidate
            
            data.append({'nber_iterations':i+1,'best_parameters': (p_new,q_new,r_new),'max_MRR':max_MRR})

            if((p == p_new) & (q == q_new) & (r == r_new)): # if best config has not changed, found local maximum, terminate
                print('yes, local maximum found')
                break
            else:
                p, q, r = p_new, q_new, r_new # else iterate
                known_configs += to_score
        df = pd.DataFrame(data)
        return df
    
    
    def LES(self,params_range): #Local exhaustive search (LES)
        l = []
        max_MRR = 0
        opt_p, opt_q, opt_r= 0,0,0
        
        
        for p in params_range:
            for q in params_range:
                for r in params_range:
                    
                    Mrr = self.MRR(p,q,r)
                    l.append((p,q,r,Mrr))
                    

                    if Mrr > max_MRR:
                        max_MRR = Mrr
                        (opt_p, opt_q, opt_r) = (p,q,r)
                        
        print('the best parameters with exaustive is',(opt_p, opt_q, opt_r))
        print('the all list is',l)
                        
        return (opt_p, opt_q, opt_r), l


    def MRR(self, p,q,r):
        '''Return the achieved MRR of Keci_r for a fixed p,q and r on the train data set'''

        
        folder_name = f"{p}_{q}_{r}"
        folder_path = os.path.join(self.folder_name, folder_name)
        
        self.run_main(p,q,r) 
            
        experiments_path = folder_path

        for folder in os.listdir(experiments_path):

            if os.path.isdir(os.path.join(experiments_path, folder)):
                folder_path = os.path.join(experiments_path, folder)
                report_path = os.path.join(folder_path, 'eval_report.json')


                if os.path.exists(report_path):
                    with open(report_path, 'r') as file:
                        report_data = json.load(file)

        return report_data['Val']['MRR']



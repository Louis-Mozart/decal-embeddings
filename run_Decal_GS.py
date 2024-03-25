from Decal import Decal_exp
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--kg", type=str, default='')

args = parser.parse_args()

path_main = "../decal-embeddings/run.py"
folder_name = f"Experiments_{args.kg}"
Experiments_path=f"../Experiments_{args.kg}"
path_dataset = f"../decal-embeddings/KGs/{args.kg}"
Num_epochs = 250
Batch_size = 1024

dat = Decal_exp(emb_dim=32,path_main = path_main,folder_name = folder_name,Experiments_path=Experiments_path,\
               num_epochs=250,batch_size=1024, scoring_technique= "KvsAll",path_dataset=path_dataset)

max_iter = 50
df_search = dat.GS(max_iter) 
df_search.to_csv(f'search_{args.kg}.csv',index=False)
print(df_search)
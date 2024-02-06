# Embedding-in-Degenerate-Clifford-Algebras
This repo shows the implementation of DeCal where we consider the embeddings in Cl_pqr Clifford algebras.
# How to use this repo?
First install all the necessary packages: pip install requirements.txt
# Example of how to run the scripts
### Run the LES algorithm: python run_Decal_LES.py --kg UMLS
### Run the GSDC algorithm: python run_Decal_GSDC.py --kg UMLS
### Run the GSDC algorithm: python run_Decal_GS.py --kg UMLS
### Run the DeCal with desired values of p,q,r : python main.py --path_dataset_folder ../decal-embeddings/KGs/FB15k-237 --p 1 --q 1 --r 5

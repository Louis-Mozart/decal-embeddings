# Embedding-in-Degenerate-Clifford-Algebras
This repo shows the implementation of the DeCal KGE model

## Installation
<details><summary> Click me! </summary>
First, make sure you have Anaconda installed

### Installation from Source
``` bash
git clone https://github.com/Louis-Mozart/decal-embeddings
conda create -n dice python=3.10.13 --no-default-packages && conda activate dice && cd Embedding-in-Degenerate-Clifford-Algebras &&
pip3 install -e .
```
or

```bash
pip install dicee
```
</details>

## Download Knowledge Graphs
```bash
wget https://files.dice-research.org/datasets/dice-embeddings/KGs.zip --no-check-certificate && unzip KGs.zip
```
# How to use this repo?
First, install all the necessary packages: pip install -r requirements.txt

# Example of how to run the scripts

### Run the LES algorithm: 
python run_Decal_LES.py --kg UMLS
### Run the GSDC algorithm:
python run_Decal_GSDC.py --kg UMLS
### Run the GSDC algorithm:
python run_Decal_GS.py --kg UMLS
### Run the DeCal with desired values of p,q,r:
python main.py --path_dataset_folder ../decal-embeddings/KGs/FB15k-237 --p 1 --q 1 --r 5

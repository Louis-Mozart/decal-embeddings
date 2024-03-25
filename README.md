# Decal Embeddings: Embeddings Knowledge Graph in Clifford Algebras

Knowledge graph embedding has shown to be succesfull when using divisional algebras ($\mathbb{R}$, $\mathbb{C}$, $\mathbb{Q}$, etc..) as these space are useful to model complex relations and pattern in a KG dataset. However, it exists no universal space to perform the embedding for all datasets as the space is congruent to the existing knowledge. Therefore, it can be difficult to decide, given a KG dataset in which space we will compute the embeddings. One existing approach **[(Keci)](https://link.springer.com/chapter/10.1007/978-3-031-43418-1_34)** already tackle this problem by performing the embedding in a Clifford Algebra $Cl_{p,q}(\mathbb{R})$. This approach already generalize over baselines such as DistMult, ComplEx etc... but cannot generalize over approaches based on dual numbers. To tackle this, we developped our approach DeCaL which performs the embeddings into a degenerate Clifford Algebra $Cl_{p,q,r}(\mathbb{R})$. These spaces, allows generalizing over approaches based on dual numbers (which cannot be modelled using $Cl_{p,q}$) and capturing patterns that emanate from the absence of higher-order interactions between real and complex parts of entity embeddings. 

For the discovery of the extra parameter p,q and r we proposed four algorithms:

## Installation
First, make sure you have anaconda installed
<details><summary> Click me! </summary>

### Installation from Source
``` bash
git clone https://github.com/Louis-Mozart/decal-embeddings
conda create -n dice python=3.10.13 --no-default-packages && conda activate dice && cd Embedding-in-Degenerate-Clifford-Algebras &&
pip3 install -e .
```

## Download Knowledge Graphs
```bash
wget https://files.dice-research.org/datasets/dice-embeddings/KGs.zip --no-check-certificate && unzip KGs.zip
```

</details>

## Knowledge Graph Embedding Models
<details> <summary> To see available Models</summary>

1. TransE, DistMult, ComplEx, ConEx, QMult, OMult, ConvO, ConvQ, Keci, DeCaL

</details>

# How to use this repo?
First install all the necessary packages: pip install -r requirements.txt
# Example of how to run the scripts
### Run the LES algorithm: 
```bash
python run_Decal_LES.py --kg UMLS
```
### Run the GSDC algorithm:
```bash
python run_Decal_GSDC.py --kg UMLS
```
### Run the GSDC algorithm:
```bash
python run_Decal_GS.py --kg UMLS
```
### Run the DeCal with desired values of p,q,r:
```bash
python main.py --path_dataset_folder ../decal-embeddings/KGs/FB15k-237 --p 1 --q 1 --r 5
```
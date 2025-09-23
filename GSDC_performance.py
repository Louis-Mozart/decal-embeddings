
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d import art3d

class show_performance:

    def __init__(self, data, time,name):

        '''Inputs: 
           time: choose among Train, Val, and Test
           data: a CSV file coming from the results_keci function'''
        
        self.data = data
        self.time = time
        self.name = name
        self.data[['p', 'q', 'r']] = self.data['Experiment'].str.split('_', expand=True).astype(int)
        self.data = self.data.drop(columns=['Experiment'])
    
        
                    
    def plot3d(self):
        """This plot will show the distribution of all G """

        fig = plt.figure(figsize=(8, 6))
        ax = fig.add_subplot(111, projection='3d')

        p = self.data['p']
        q = self.data['q']
        r = self.data['r']
        mrr = self.data[f'{self.time}_MRR']

        scatter = ax.scatter(p, q, r, c=mrr, cmap='viridis', marker='o')

        ax.set_xlabel('p', fontsize=20)  
        ax.set_ylabel('q', fontsize=20)  
        ax.set_zlabel('r', fontsize=20) 

        # Increase tick label font size for all axes
        ax.tick_params(axis='both', which='major', labelsize=14)  # Adjust fontsize as needed

        # Set fontsize for z-axis ticks specifically
        ax.tick_params(axis='z', labelsize=14)  #
      
        ax.xaxis.set_major_locator(plt.MaxNLocator(integer=True))
        ax.yaxis.set_major_locator(plt.MaxNLocator(integer=True))
        ax.zaxis.set_major_locator(plt.MaxNLocator(integer=True))

        cbar = fig.colorbar(scatter, ax=ax, pad=0.1, shrink=0.7)
        cbar.ax.tick_params(labelsize=14) 
        cbar.set_label('MRR',fontsize = 26)

        plt.savefig(f'{self.name}_{self.time}.pdf', bbox_inches='tight')  

        plt.show()
        
        
        
    def topk_triples(self,latex,k):
        
        time = self.time
       
        time_data = self.data[['p', 'q', 'r',f'{time}_H@1',f'{time}_H@3',f'{time}_H@10',f'{time}_MRR']]
        
        time_data_sorted = time_data.sort_values(by=f'{time}_MRR', ascending=False)
        
        if latex == True:
            topk = time_data_sorted.head(k).to_latex(index = False)
        else:
            topk = time_data_sorted.head(k)
        
        return topk
        


    

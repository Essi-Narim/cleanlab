
# coding: utf-8

# ## The RankPruning algorithm class for multiclass learning with noisy labels. 
# #### The RankPruning class wraps around an instantion of a classifier. Your classifier must adhere to the sklearn template, meaning it must define three functions:
# * clf.fit(X, y, sample_weight = None)
# * clf.predict_proba(X)
# * clf.predict(X)
# * clf.predict(X)
# 
# where 'X' (of length n) contains your data, 'y' (of length n) contains your targets formatted as 0, 1, 2, ..., K-1, and sample_weight (of length n) that reweights examples in the loss function while training.
# 
# ## Confidence
# 
# There are two new notions of confidence in this package
# 1. Confident examples -- examples we are confident are labeled correctly. We prune everything else. Comptuationally, this means keeping the examples with `high probability of belong to their provided label class'.
# 2. Confident errors -- examples we are confident are labeled incorrectly. We prune these. Comptuationally, this means pruning the examples with `high probability of belong to a different class'. 
# 
# ## Example
# 
# ```python
# from cleanlab.classification import RankPruning
# from sklearn.linear_model import LogisticRegression as logreg
# 
# rp = RankPruning(clf=logreg()) # Pass in any classifier. Yup, neural networks work, too.
# rp.fit(X_train, y_may_have_label_errors)
# pred = rp.predict(X_test) # Estimates the predictions you would have gotten had you trained without label errors.
# ```
# 
# ## Notes
# 
# * s - denotes *noisy labels*, just means training labels, but maybe with label errors
# * Class labels (K classes) must be formatted as natural numbers: 0, 1, 2, ..., K-1
# 
# 
# 
# ### The easiest way to use any model (Tensorflow, caffe2, PyTorch, etc.) with `cleanlab` is to wrap it in a class that inherets the `sklearn.base.BaseEstimator`:
# ```python
# from sklearn.base import BaseEstimator
# class YourModel(BaseEstimator): # Inherits sklearn base classifier
#     def __init__(self, ):
#         pass
#     def fit(self, X, y, sample_weight = None):
#         pass
#     def predict(self, X):
#         pass
#     def predict_proba(self, X):
#         pass
#     def score(self, X, y, sample_weight = None):
#         pass
# ```

# In[ ]:


from __future__ import print_function, absolute_import, division, unicode_literals, with_statement

from sklearn.linear_model import LogisticRegression as logreg
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import accuracy_score
import numpy as np
import inspect

from cleanlab.util import assert_inputs_are_valid, value_counts, remove_noise_from_class
from cleanlab.latent_estimation import     estimate_py_noise_matrices_and_cv_pred_proba,     estimate_py_and_noise_matrices_from_probabilities,     estimate_cv_predicted_probabilities
from cleanlab.latent_algebra import compute_py_inv_noise_matrix, compute_noise_matrix_from_inverse
from cleanlab.pruning import get_noise_indices


# In[ ]:


from sklearn.base import BaseEstimator

class RankPruning(BaseEstimator): # Inherits sklearn classifier
    '''Rank Pruning is a state-of-the-art algorithm (2017) for 
      multiclass classification with (potentially extreme) mislabeling 
      across any or all pairs of class labels. It works with ANY classifier,
      including deep neural networks. See clf parameter.
    This subfield of machine learning is referred to as Confident Learning.
    Rank Pruning also achieves state-of-the-art performance for binary
      classification with noisy labels and positive-unlabeled
      learning (PU learning) where a subset of positive examples is given and
      all other examples are unlabeled and assumed to be negative examples.
    Rank Pruning works by "learning from confident examples." Confident examples are
      identified as examples with high predicted probability for their training label.
    Given any classifier having the predict_proba() method, an input feature matrix, X, 
      and a discrete vector of labels, s, which may contain mislabeling, Rank Pruning 
      estimates the classifications that would be obtained if the hidden, true labels, y,
      had instead been provided to the classifier during training.
    "s" denotes the noisy label instead of \tilde(y), for ASCII encoding reasons.

    Parameters 
    ----------
    clf : sklearn.classifier or equivalent class
      The clf object must have the following three functions defined:
      1. clf.predict_proba(X) # Predicted probabilities
      2. clf.predict(X) # Predict labels
      3. clf.fit(X, y, sample_weight) # Train classifier
      Stores the classifier used in Rank Pruning.
      Default classifier used is logistic regression.
        
    seed : int (default = None)
      Number to set the default state of the random number generator used to split
      the cross-validated folds. If None, uses np.random current random state.
          
    cv_n_folds : int
      This class needs holdout predicted probabilities for every training example
      and f not provided, uses cross-validation to compute them. cv_n_folds sets
      the number of cross-validation folds used to compute
      out-of-sample probabilities for each example in X.

    prune_method : str (default: 'prune_by_noise_rate')
      'prune_by_class', 'prune_by_noise_rate', or 'both'. Method used for pruning.
      1. 'prune_by_noise_rate': works by removing examples with *high probability* of
      being mislabeled for every non-diagonal in the prune_counts_matrix (see pruning.py).
      2. 'prune_by_class': works by removing the examples with *smallest probability* of
      belonging to their given class label for every class.
      3. 'both': Finds the examples satisfying (1) AND (2) and removes their set conjunction. 

    prune_count_method : str (default 'inverse_nm_dot_s')
      Options are 'inverse_nm_dot_s' or 'calibrate_confident_joint'. 
      Determines the method used to estimate the counts of the joint P(s, y) that will 
      be used to determine how many examples to prune
      for every class that are flipped to every other class, as follows:
        if prune_count_method == 'inverse_nm_dot_s':
          prune_count_matrix = inverse_noise_matrix * s_counts # Matrix of counts(y=k and s=l)
        elif prune_count_method == 'calibrate_confident_joint':# calibrate
          prune_count_matrix = confident_joint.T / float(confident_joint.sum()) * len(s) 

    converge_latent_estimates : bool (Default: False)
      If true, forces numerical consistency of latent estimates. Each is estimated
      independently, but they are related mathematically with closed form 
      equivalences. This will iteratively enforce mathematically consistency.

    pulearning : int
      Set to the integer of the class that is perfectly labeled, if such
      a class exists. Otherwise, or if you are unsure, 
      leave pulearning = None (default).'''  
  
  
    def __init__(
        self, 
        clf = None, 
        seed = None,
        # Hyper-parameters (used by .fit() function)
        cv_n_folds = 5,
        prune_method = 'prune_by_noise_rate',
        prune_count_method = 'inverse_nm_dot_s',
        converge_latent_estimates = False,
        pulearning = None,
    ):
        
        if clf is None:
            clf = logreg() # Use logistic regression if no classifier is provided.
        
        # Make sure the passed in classifier has the appropriate methods defined.
        if not hasattr(clf, "fit"):
            raise ValueError('The classifier (clf) must define a .fit() method.')
        if not hasattr(clf, "predict_proba"):
            raise ValueError('The classifier (clf) must define a .predict_proba() method.')
        if not hasattr(clf, "predict"):
            raise ValueError('The classifier (clf) must define a .predict() method.')
        
        if seed is not None:
            np.random.seed(seed = seed)
        
        self.clf = clf
        self.seed = seed
        self.cv_n_folds = cv_n_folds
        self.prune_method = prune_method
        self.prune_count_method = prune_count_method
        self.converge_latent_estimates = converge_latent_estimates
        self.pulearning = pulearning
  
  
    def fit(
        self, 
        X,
        s,
        psx = None,
        thresholds = None,
        noise_matrix = None,
        inverse_noise_matrix = None, 
    ):
        '''This method implements the Rank Pruning mantra 'learning with confident examples.'
        This function fits the classifer (self.clf) to (X, s) accounting for the noise in
        both the positive and negative sets.

        Parameters
        ----------
        X : np.array
          Input feature matrix (N, D), 2D numpy array

        s : np.array
          A binary vector of labels, s, which may contain mislabeling. 

        psx : np.array (shape (N, K))
          P(s=k|x) is a matrix with K (noisy) probabilities for each of the N examples x.
          This is the probability distribution over all K classes, for each
          example, regarding whether the example has label s==k P(s=k|x). psx should
          have been computed using 3 (or higher) fold cross-validation.
          If you are not sure, leave psx = None (default) and
          it will be computed for you using cross-validation.

        thresholds : iterable (list or np.array) of shape (K, 1)  or (K,)
          P(s^=k|s=k). If an example has a predicted probability "greater" than
          this threshold, it is counted as having hidden label y = k. This is
          not used for pruning, only for estimating the noise rates using
          confident counts. This value should be between 0 and 1. Default is None.

        noise_matrix : np.array of shape (K, K), K = number of classes
          A conditional probablity matrix of the form P(s=k_s|y=k_y) containing
          the fraction of examples in every class, labeled as every other class.
          Assumes columns of noise_matrix sum to 1. 
    
        inverse_noise_matrix : np.array of shape (K, K), K = number of classes
          A conditional probablity matrix of the form P(y=k_y|s=k_s) representing
          the estimated fraction observed examples in each class k_s, that are
          mislabeled examples from every other class k_y. If None, the 
          inverse_noise_matrix will be computed from psx and s.
          Assumes columns of inverse_noise_matrix sum to 1.

        Output
        ------
          Returns (noise_mask, sample_weight)'''
    
        # Check inputs
        assert_inputs_are_valid(X, s, psx)
        if noise_matrix is not None and np.trace(noise_matrix) <= 1:
            raise Exception("Trace(noise_matrix) must exceed 1.")
        if inverse_noise_matrix is not None and np.trace(inverse_noise_matrix) <= 1:
            raise Exception("Trace(inverse_noise_matrix) must exceed 1.")

        # Number of classes
        self.K = len(np.unique(s))

        # 'ps' is p(s=k)
        self.ps = value_counts(s) / float(len(s))

        self.confident_joint = None
        # If needed, compute noise rates (fraction of mislabeling) for all classes. 
        # Also, if needed, compute P(s=k|x), denoted psx.
        
        # Set / re-set noise matrices / psx; estimate if not provided.
        if noise_matrix is not None:
            self.noise_matrix = noise_matrix
            if inverse_noise_matrix is None:
                self.py, self.inverse_noise_matrix = compute_py_inv_noise_matrix(self.ps, self.noise_matrix)
        if inverse_noise_matrix is not None:
            self.inverse_noise_matrix = inverse_noise_matrix
            if noise_matrix is None:
                self.noise_matrix = compute_noise_matrix_from_inverse(self.ps, self.inverse_noise_matrix)
        if noise_matrix is None and inverse_noise_matrix is None:
            if psx is None:
                self.py, self.noise_matrix, self.inverse_noise_matrix, self.confident_joint, psx =                 estimate_py_noise_matrices_and_cv_pred_proba(
                    X = X, 
                    s = s, 
                    clf = self.clf,
                    cv_n_folds = self.cv_n_folds,
                    thresholds = thresholds, 
                    converge_latent_estimates = self.converge_latent_estimates,
                    seed = self.seed,
                )
            else: # psx is provided by user (assumed holdout probabilities)
                self.py, self.noise_matrix, self.inverse_noise_matrix, self.confident_joint =                 estimate_py_and_noise_matrices_from_probabilities(
                    s = s, 
                    psx = psx,
                    thresholds = thresholds, 
                    converge_latent_estimates = self.converge_latent_estimates,
                )

        if psx is None: 
            psx = estimate_cv_predicted_probabilities(
                X = X, 
                labels = s, 
                clf = self.clf,
                cv_n_folds = self.cv_n_folds,
                seed = self.seed,
            ) 

        # Zero out noise matrix entries if pulearning = the integer specifying the class without noise.
        if self.pulearning is not None:
            self.noise_matrix = remove_noise_from_class(self.noise_matrix, class_without_noise=self.pulearning)
            # TODO: self.inverse_noise_matrix = remove_noise_from_class(self.inverse_noise_matrix, class_without_noise=self.pulearning)

        # This is the actual work of this function.

        # Get the indices of the examples we wish to prune
        self.noise_mask = get_noise_indices(
            s, 
            psx, 
            inverse_noise_matrix = self.inverse_noise_matrix, 
            confident_joint = self.confident_joint,
            prune_method = self.prune_method, 
            prune_count_method = self.prune_count_method,
            converge_latent_estimates = self.converge_latent_estimates,
        ) 

        X_mask = ~self.noise_mask
        X_pruned = X[X_mask]
        s_pruned = s[X_mask]
        
        # Check if sample_weight in clf.fit(). Compatible with Python 2/3.
        if hasattr(inspect, 'getfullargspec') and             'sample_weight' in inspect.getfullargspec(self.clf.fit).args or             hasattr(inspect, 'getargspec') and             'sample_weight' in inspect.getargspec(self.clf.fit).args:       
            # Re-weight examples in the loss function for the final fitting
            # s.t. the "apparent" original number of examples in each class
            # is preserved, even though the pruned sets may differ.
            self.sample_weight = np.ones(np.shape(s_pruned))
            for k in range(self.K): 
                self.sample_weight[s_pruned == k] = 1.0 / self.noise_matrix[k][k]

            self.clf.fit(X_pruned, s_pruned, sample_weight=self.sample_weight)
        else:
            # This is less accurate, but its all we can do if sample_weight isn't available.
            self.clf.fit(X_pruned, s_pruned)
            
        return self.clf
    
    
    def predict(self, *args, **kwargs):
        '''Returns a binary vector of predictions.

        Typical Parameters
        ----------
        X : np.array of shape (n, m)
          The test data as a feature matrix.'''

        return self.clf.predict(*args, **kwargs)
  
  
    def predict_proba(self, *args, **kwargs):
        '''Returns a vector of probabilties P(y=k)
        for each example in X.

        Typical Parameters
        ----------
        X : np.array of shape (n, m)
          The test data as a feature matrix.'''

        return self.clf.predict_proba(*args, **kwargs)
    
    
    def score(self, X, y, sample_weight=None):
        '''Returns the clf's score on a test set X with labels y.

        Parameters
        ----------
        X : np.array of shape (n, m)
          The test data as a feature matrix.
          
        y : np.array<int> of shape (n,) or (n, 1)
          The test classification labels as an array.
          
        sample_weight : np.array<float> of shape (n,) or (n, 1)
          Weights each example when computing the score / accuracy.'''
        
        if hasattr(self.clf, 'score'):        
            if 'sample_weight' in inspect.getfullargspec(self.clf.score).args:
                return self.clf.score(X, y, sample_weight=sample_weight)
            else:
                return self.clf.score(X, y)
        else:
            return accuracy_score(y, self.clf.predict(X_val), sample_weight=sample_weight) 


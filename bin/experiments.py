import numpy as np
import os
from scanorama import visualize
from sklearn.cluster import KMeans
from sklearn.preprocessing import LabelEncoder
import sys

from sketch import *
from utils import *

# Clustering-based downsampling efficiency.
def cluster_efficiency(cluster_labels, auto_labels):
    assert(len(cluster_labels) == len(auto_labels))

    clusters = sorted(set(cluster_labels))
    autos = sorted(set(auto_labels))

    # Assign indices to clusters and autos.
    cluster_idx = {
        cluster: i for i, cluster in enumerate(clusters)
    }
    auto_idx = {
        auto: j for j, auto in enumerate(autos)
    }

    # Count cluster-auto pairs.
    table = np.zeros((len(cluster_idx), len(auto_idx)))
    for cluster, auto in zip(cluster_labels, auto_labels):
        i = cluster_idx[cluster]
        j = auto_idx[auto]
        table[i, j] += 1

    # Map clusters to efficiencies.
    cluster_to_efficiency = {}
    for i, cluster in enumerate(clusters):

        n_cluster_in_auto = []
        pct_cluster_in_auto = []
        for j, auto in enumerate(autos):
            n_auto = sum(table[:, j])
            n_in_auto = table[i, j]
            pct_in_auto = float(n_in_auto) / float(n_auto)
    
            n_cluster_in_auto.append(n_in_auto)
            pct_cluster_in_auto.append(pct_in_auto)

        wsum = np.dot(n_cluster_in_auto, pct_cluster_in_auto)
        assert(sum(n_cluster_in_auto) == sum(table[i, :]))
        cluster_to_efficiency[cluster] = (
            float(wsum) / float(sum(n_cluster_in_auto))
        )

    return cluster_to_efficiency

def experiment_efficiency_kmeans(X_dimred, cluster_labels):
    log('k-means clustering efficiency experiment...')
    
    cluster_labels = np.array(cluster_labels)
    k_c_e = {}
    kmeans_ks = [ 5, 10, 20, 30, 40, 50, 100 ]
    
    for kmeans_k in kmeans_ks:
        log('k = {}'.format(kmeans_k))

        km = KMeans(n_clusters=kmeans_k, n_jobs=40, verbose=0)
        km.fit(X_dimred)

        log('Calculating cluster efficiencies for k = {}'
            .format(kmeans_k))

        k_c_e[kmeans_k] = cluster_efficiency(
            cluster_labels, km.labels_
        )

    for k in sorted(k_c_e.keys()):
        print('k = {}'.format(k))
        for c in sorted(k_c_e[k].keys()):
            print('\tcluster = {}, efficiency = {}'
                  .format(c, k_c_e[k][c]))

    log('k-means clustering efficiency experiment done.')

    return k_c_e

def experiment_efficiency_louvain(X_dimred, cluster_labels):
    from anndata import AnnData
    import scanpy.api as sc

    log('Louvain clustering efficiency experiment...')

    cluster_labels = np.array(cluster_labels)

    adata = AnnData(X=X_dimred)
    sc.pp.neighbors(adata, use_rep='X')

    r_c_e = {}
    resolutions = [ 0.1, 0.5, 1, 1.5, 2, 5 ]

    for resolution in resolutions:
        log('resolution = {}'.format(resolution))

        sc.tl.louvain(adata, resolution=resolution,
                      key_added='louvain')
        louvain_labels = np.array(adata.obs['louvain'].tolist())

        log('Found {} clusters'.format(len(set(louvain_labels))))
        log('Calculating cluster efficiencies for resolution = {}'
            .format(resolution))

        r_c_e[resolution] = cluster_efficiency(
            cluster_labels, louvain_labels
        )

    for r in sorted(r_c_e.keys()):
        print('resolution = {}'.format(r))
        for c in sorted(r_c_e[r].keys()):
            print('\tcluster = {}, efficiency = {}'
                  .format(c, r_c_e[r][c]))

    log('Louvain clustering efficiency experiment done.')

    return r_c_e

def report_cluster_counts(cluster_labels):
    clusters = sorted(set(cluster_labels))

    for cluster in clusters:
        n_cluster = sum(cluster_labels == cluster)
        print('Cluster {} has {} cells'.
              format(cluster, n_cluster))

def experiment_srs(X_dimred, name, cell_labels=None,
                   kmeans=True, visualize_orig=True,
                   downsample=True, n_downsample=100000,
                   gene_names=None, gene_expr=None, genes=None,
                   perplexity=500, kmeans_k=10):

    # Assign cells to clusters.

    if kmeans or \
       not os.path.isfile('data/cell_labels/{}.txt'.format(name)):
        log('K-means...')
        km = KMeans(n_clusters=kmeans_k, n_jobs=10, verbose=0)
        km.fit(X_dimred)
        np.savetxt('data/cell_labels/{}.txt'.format(name), km.labels_)

    if cell_labels is None:
        cell_labels = (
            open('data/cell_labels/{}.txt'.format(name))
            .read().rstrip().split()
        )
        le = LabelEncoder().fit(cell_labels)
        cell_labels = le.transform(cell_labels)
        cell_types = le.classes_
    else:
        cell_types = [ str(ct) for ct in sorted(set(cell_labels)) ]

    # Visualize original data.
    
    if visualize_orig:
        log('Visualizing original...')
     
        if downsample and X_dimred.shape[0] > n_downsample:
            log('Visualization will downsample to {}...'
                .format(n_downsample))
            idx = np.random.choice(
                X_dimred.shape[0], size=n_downsample, replace=False
            )
        else:
            idx = range(X_dimred.shape[0])

        if not gene_names is None and \
           not gene_expr is None and \
           not genes is None:
            expr = gene_expr[idx, :]
        else:
            expr = None
     
        embedding = visualize(
            [ X_dimred[idx, :] ], cell_labels[idx],
            name + '_orig{}'.format(len(idx)), cell_types,
            gene_names=gene_names, gene_expr=expr, genes=genes,
            perplexity=perplexity, n_iter=500, image_suffix='.png'
        )
        np.savetxt('data/embedding_{}.txt'.format(name), embedding)

    # Downsample while preserving structure and visualize.

    Ns = [ 1000, 5000, 10000, 20000, 50000 ]

    for N in Ns:
        if N >= X_dimred.shape[0]:
            continue

        log('SRS {}...'.format(N))
        srs_idx = srs(X_dimred, N)
        log('Found {} entries'.format(len(set(srs_idx))))

        log('Visualizing sampled...')

        if not gene_names is None and \
           not gene_expr is None and \
           not genes is None:
            expr = gene_expr[srs_idx, :]
        else:
            expr = None

        visualize([ X_dimred[srs_idx, :] ], cell_labels[srs_idx],
                  name + '_srs{}'.format(N), cell_types,
                  gene_names=gene_names, gene_expr=expr, genes=genes,
                  perplexity=max(N/200, 50), n_iter=500,
                  size=max(int(30000/N), 1), image_suffix='.png')

        report_cluster_counts(cell_labels[srs_idx])

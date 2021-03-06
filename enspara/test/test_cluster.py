from __future__ import print_function, division, absolute_import

import unittest
import warnings
import time
import os

import numpy as np
import mdtraj as md
from mdtraj.testing import get_fn

from nose.tools import (assert_raises, assert_less, assert_true, assert_is,
                        assert_equal)
from nose.plugins.attrib import attr

from sklearn.datasets import make_blobs

from numpy.testing import assert_array_equal, assert_allclose

from ..cluster.hybrid import KHybrid, hybrid
from ..cluster import kcenters, kmedoids, util
from ..exception import DataInvalid, ImproperlyConfigured


class TestTrajClustering(unittest.TestCase):

    def setUp(self):
        self.trj_fname = get_fn('frame0.xtc')
        self.top_fname = get_fn('native.pdb')

        self.trj = md.load(self.trj_fname, top=self.top_fname)

    def test_kcenters_object(self):
        # '''
        # KHybrid() clusterer should produce correct output.
        # '''
        N_CLUSTERS = 5
        CLUSTER_RADIUS = 0.1

        with assert_raises(ImproperlyConfigured):
            kcenters.KCenters(metric=md.rmsd)

        # Test n clusters
        clustering = kcenters.KCenters(
            metric=md.rmsd,
            n_clusters=N_CLUSTERS)

        clustering.fit(self.trj)

        assert hasattr(clustering, 'result_')
        assert len(np.unique(clustering.labels_)) == N_CLUSTERS, \
            clustering.labels_

        # Test dist_cutoff
        clustering = kcenters.KCenters(
            metric=md.rmsd,
            cluster_radius=CLUSTER_RADIUS)

        clustering.fit(self.trj)

        assert hasattr(clustering, 'result_')
        assert clustering.distances_.max() < CLUSTER_RADIUS, \
            clustering.distances_

        # Test n clusters and dist_cutoff
        clustering = kcenters.KCenters(
            metric=md.rmsd,
            n_clusters=N_CLUSTERS,
            cluster_radius=CLUSTER_RADIUS)

        clustering.fit(self.trj)

        # In this particular case, the clustering should cut off at 5 clusters
        # despite not reaching the distance cutoff
        assert hasattr(clustering, 'result_')
        assert len(np.unique(clustering.labels_)) == N_CLUSTERS, \
            clustering.labels_

    def test_khybrid_object(self):
        # '''
        # KHybrid() clusterer should produce correct output.
        # '''
        N_CLUSTERS = 5

        with assert_raises(ImproperlyConfigured):
            KHybrid(metric=md.rmsd, kmedoids_updates=10)

        clustering = KHybrid(
            metric=md.rmsd,
            n_clusters=N_CLUSTERS,
            kmedoids_updates=10,
            random_state=99)

        clustering.fit(self.trj)

        assert hasattr(clustering, 'result_')
        assert len(np.unique(clustering.labels_)) == N_CLUSTERS, \
            clustering.labels_

        self.assertAlmostEqual(
            np.average(clustering.distances_), 0.09, delta=0.005)
        self.assertAlmostEqual(
            np.std(clustering.distances_), 0.0185, delta=0.005)

        with self.assertRaises(DataInvalid):
            clustering.result_.partition([5, 10])

        presult = clustering.result_.partition([len(self.trj)-100, 100])

        self.assertTrue(np.all(
            presult.distances[0] == clustering.distances_[0:-100]))

        self.assertTrue(
            np.all(presult.assignments[0] == clustering.labels_[0:-100]))

        self.assertEqual(len(presult.center_indices[0]), 2)

    def test_kmedoids(self):
        '''
        Check that pure kmedoid clustering is behaving as expected on
        md.Trajectory objects.
        '''

        N_CLUSTERS = 5

        result = kmedoids.kmedoids(
            self.trj,
            distance_method='rmsd',
            n_clusters=N_CLUSTERS,
            n_iters=1000)

        # kcenters will always produce the same number of clusters on
        # this input data (unchanged by kmedoids updates)
        self.assertEqual(len(np.unique(result.assignments)), N_CLUSTERS)

        self.assertAlmostEqual(
            np.average(result.distances), 0.085, delta=0.01)
        self.assertAlmostEqual(
            np.std(result.distances), 0.019, delta=0.005)

    def test_hybrid(self):
        '''
        Clustering works on md.Trajectories.
        '''
        N_CLUSTERS = 5

        result = hybrid(
            self.trj,
            distance_method='rmsd',
            init_centers=None,
            n_clusters=N_CLUSTERS,
            random_first_center=False,
            n_iters=5,
            random_state=0)

        # kcenters will always produce the same number of clusters on
        # this input data (unchanged by kmedoids updates)
        assert_equal(len(np.unique(result.assignments)), N_CLUSTERS)

        assert_less(round(result.distances.mean(), 7), 0.094)
        assert_less(np.std(result.distances), 0.019)

    def test_kcenters_maxdist(self):
        result = kcenters.kcenters(
            self.trj,
            distance_method='rmsd',
            init_centers=None,
            dist_cutoff=0.1,
            random_first_center=False
            )

        self.assertEqual(len(np.unique(result.assignments)), 17)

        # this is simlar to asserting the distribution of distances.
        # since KCenters is deterministic, this shouldn't ever change?
        self.assertAlmostEqual(np.average(result.distances),
                               0.074690734158752686)
        self.assertAlmostEqual(np.std(result.distances),
                               0.018754008455304401)

    def test_kcenters_nclust(self):
        N_CLUSTERS = 3

        result = kcenters.kcenters(
            self.trj,
            distance_method='rmsd',
            n_clusters=N_CLUSTERS,
            init_centers=None,
            random_first_center=False
            )

        self.assertEqual(len(np.unique(result.assignments)), N_CLUSTERS)

        # this is simlar to asserting the distribution of distances.
        # since KCenters is deterministic, this shouldn't ever change?
        self.assertAlmostEqual(np.average(result.distances),
                               0.10387578309920734)
        self.assertAlmostEqual(np.std(result.distances),
                               0.018355072790569946)

@attr('mpi')
def test_kcenters_mpi_traj():
    from ..mpi import MPI
    MPI_RANK = MPI.COMM_WORLD.Get_rank()
    MPI_SIZE = MPI.COMM_WORLD.Get_size()

    trj = md.load(get_fn('frame0.h5'))

    data = trj[MPI_RANK::MPI_SIZE]

    r = kcenters.kcenters_mpi(data, md.rmsd, n_clusters=10)
    world_distances, world_assignments, world_ctr_inds = r

    mpi_assigs = np.empty((len(trj),), dtype=world_assignments.dtype)
    mpi_dists = np.empty((len(trj),), dtype=world_distances.dtype)
    mpi_ctr_inds = [(i*MPI_SIZE)+r for r, i in world_ctr_inds]

    try:
        np.save('assig%s.npy' % MPI_RANK, world_assignments)
        np.save('dists%s.npy' % MPI_RANK, world_distances)
        MPI.COMM_WORLD.Barrier()

        for i in range(MPI_SIZE):
            mpi_assigs[i::MPI_SIZE] = np.load('assig%s.npy' % i)
            mpi_dists[i::MPI_SIZE] = np.load('dists%s.npy' % i)
    finally:
        MPI.COMM_WORLD.Barrier()
        os.remove('assig%s.npy' % MPI_RANK)
        os.remove('dists%s.npy' % MPI_RANK)

    if MPI_RANK == 0:
        r = kcenters.kcenters(trj, md.rmsd, n_clusters=10)

        assert_array_equal(mpi_assigs, r.assignments)
        assert_array_equal(mpi_dists, r.distances)
        assert_array_equal(mpi_ctr_inds, r.center_indices)


@attr('mpi')
def test_kcenters_mpi_numpy():
    from ..mpi import MPI
    MPI_RANK = MPI.COMM_WORLD.Get_rank()
    MPI_SIZE = MPI.COMM_WORLD.Get_size()

    trj = md.load(get_fn('frame0.h5')).xyz[:, :, 0].copy()

    data = trj[MPI_RANK::MPI_SIZE]

    def euc(X, x):
        return np.square(X -x).sum(axis=1)

    r = kcenters.kcenters_mpi(data, euc, n_clusters=10)
    world_distances, world_assignments, world_ctr_inds = r

    mpi_assigs = np.empty((len(trj),), dtype=world_assignments.dtype)
    mpi_dists = np.empty((len(trj),), dtype=world_distances.dtype)
    mpi_ctr_inds = [(i*MPI_SIZE)+r for r, i in world_ctr_inds]

    try:
        np.save('assig%s.npy' % MPI_RANK, world_assignments)
        np.save('dists%s.npy' % MPI_RANK, world_distances)
        MPI.COMM_WORLD.Barrier()

        for i in range(MPI_SIZE):
            mpi_assigs[i::MPI_SIZE] = np.load('assig%s.npy' % i)
            mpi_dists[i::MPI_SIZE] = np.load('dists%s.npy' % i)
    finally:
        MPI.COMM_WORLD.Barrier()
        os.remove('assig%s.npy' % MPI_RANK)
        os.remove('dists%s.npy' % MPI_RANK)

    if MPI_RANK == 0:
        r = kcenters.kcenters(trj, euc, n_clusters=10)

        assert_array_equal(mpi_assigs, r.assignments)
        assert_array_equal(mpi_dists, r.distances)
        assert_array_equal(mpi_ctr_inds, r.center_indices)


@attr('mpi')
def test_kmedoids_update_mpi_mdtraj():
    from ..mpi import MPI
    MPI_RANK = MPI.COMM_WORLD.Get_rank()
    MPI_SIZE = MPI.COMM_WORLD.Get_size()

    trj = md.load(get_fn('frame0.h5'))
    DIST_FUNC = md.rmsd

    data = trj[MPI_RANK::MPI_SIZE]

    r = kcenters.kcenters_mpi(data, DIST_FUNC, n_clusters=10)
    local_distances, local_assignments, local_ctr_inds = r

    proposals = []
    r = kcenters.kcenters(trj, DIST_FUNC, n_clusters=len(local_ctr_inds))
    global_assignments = r.assignments
    for cid in range(len(r.center_indices)):
        first_point = np.where(global_assignments == cid)[0][0]
        proposals.append((first_point % MPI_SIZE, first_point // MPI_SIZE))

    r = kmedoids._kmedoids_pam_update(
        X=data, metric=DIST_FUNC,
        medoid_inds=local_ctr_inds,
        assignments=local_assignments,
        distances=local_distances,
        proposals=proposals,
        )

    local_ctr_inds, local_distances, local_assignments = r

    mpi_ctr_inds = [(i*MPI_SIZE)+r for r, i in local_ctr_inds]

    expected_inds = [  0,  37, 400, 105,  12, 327, 242, 346,  42,   3]
    assert_array_equal(mpi_ctr_inds, expected_inds)

    true_assigs, true_dists = util.assign_to_nearest_center(
        trj, trj[mpi_ctr_inds], DIST_FUNC)

    assert_allclose(local_assignments, true_assigs[MPI_RANK::MPI_SIZE])
    assert_allclose(local_distances, true_dists[MPI_RANK::MPI_SIZE],
                    rtol=1e-06, atol=1e-03)


@attr('mpi')
def test_kmedoids_update_mpi_numpy():
    from ..mpi import MPI_RANK, MPI_SIZE

    means = [(0, 0), (0, 10), (10, 0)]
    X, y = make_blobs(centers=means, random_state=1, n_samples=20)

    data = X[MPI_RANK::MPI_SIZE]

    def DIST_FUNC(X, x):
        return np.square(X - x).sum(axis=1)

    r = kcenters.kcenters_mpi(data, DIST_FUNC, n_clusters=3)
    local_distances, local_assignments, local_ctr_inds = r

    proposals = []
    for cid in range(len(means)):
        first_point = np.where(y == cid)[0][0]
        proposals.append((first_point % MPI_SIZE, first_point // MPI_SIZE))

    r = kmedoids._kmedoids_pam_update(
        X=data, metric=DIST_FUNC,
        medoid_inds=local_ctr_inds,
        assignments=local_assignments,
        distances=local_distances,
        proposals=proposals)

    local_ctr_inds, local_distances, local_assignments = r
    mpi_ctr_inds = [(i*MPI_SIZE)+r for r, i in local_ctr_inds]

    assert_array_equal(
        mpi_ctr_inds,
        [ 0,  3, 19])

    true_assigs, true_dists = util.assign_to_nearest_center(
        X, X[mpi_ctr_inds], DIST_FUNC)

    assert_allclose(local_assignments, true_assigs[MPI_RANK::MPI_SIZE])
    assert_allclose(local_distances, true_dists[MPI_RANK::MPI_SIZE],
                    rtol=1e-06, atol=1e-03)


@attr('mpi')
def test_kmedoids_update_mpi_numpy_separated_blobs():
    from ..mpi import MPI, MPI_RANK, MPI_SIZE

    # build blobs such that each node owns only one blob.
    X, y = make_blobs(centers=[(10*MPI_RANK, 10*MPI_RANK)],
                      cluster_std=0.5,
                      random_state=0,
                      n_samples=20)

    def DIST_FUNC(X, x):
        return np.square(X - x).sum(axis=1)

    r = kcenters.kcenters_mpi(X, DIST_FUNC, n_clusters=MPI_SIZE)
    local_distances, local_assignments, local_ctr_inds = r

    r = kmedoids._kmedoids_pam_update(
        X=X, metric=DIST_FUNC,
        medoid_inds=local_ctr_inds,
        assignments=local_assignments,
        distances=local_distances,
        random_state=0,
        )

    local_ctr_inds, local_distances, local_assignments = r
    # mpi_ctr_inds = [len(X)*r + i for r, i in local_ctr_inds]

    assignments = np.concatenate(MPI.COMM_WORLD.allgather(local_assignments))
    distances = np.concatenate(MPI.COMM_WORLD.allgather(local_distances))

    for i in range(MPI_SIZE):
        if i == 0:
            cid_for_rank = 0
        else:
            cid_for_rank = assignments[i*len(X)]
        assert_array_equal(assignments[i*len(X):(i*len(X))+len(X)],
                           [cid_for_rank]*len(X))

    assert_array_equal(np.bincount(assignments), [len(X)]*MPI_SIZE)

    print(distances)
    assert np.all(distances < 6), np.where(distances >= 6)


def test_kmedoids_pam_update_numpy():

    def DIST_FUNC(X, x):
        return np.square(X - x).sum(axis=1)

    means = [(0, 0), (0, 10), (10, 0)]
    X, y = make_blobs(centers=means, random_state=0)

    r = kcenters.kcenters(X, DIST_FUNC, n_clusters=3)
    ind = r.center_indices
    assig = r.assignments
    dists = r.distances

    ind, dists, assig = kmedoids._kmedoids_pam_update(
        X, DIST_FUNC, ind, assig, dists, random_state=0)

    assert_array_equal(ind, [0, 7, 17])

    expect_assig, expect_dists = util.assign_to_nearest_center(
        X, X[ind], DIST_FUNC)

    assert_array_equal(np.unique(assig), np.arange(len(means)))
    assert_array_equal(assig, expect_assig)
    assert_array_equal(dists, expect_dists)


def test_kmedoids_pam_update_mdtraj():

    DIST_FUNC = md.rmsd

    X = md.load(get_fn('frame0.h5'))

    r = kcenters.kcenters(X, DIST_FUNC, n_clusters=3)
    ind = r.center_indices
    assig = r.assignments
    dists = r.distances

    ind, dists, assig = kmedoids._kmedoids_pam_update(
        X, DIST_FUNC, ind, assig, dists, random_state=0)

    assert_array_equal(ind, [298,  44, 341])

    expect_assig, expect_dists = util.assign_to_nearest_center(
        X, X[ind], DIST_FUNC)

    assert_array_equal(np.unique(assig), np.arange(3))
    assert_array_equal(assig, expect_assig)
    assert_allclose(dists, expect_dists, atol=1e-6)


class TestNumpyClustering(unittest.TestCase):

    generators = [(1, 1), (10, 10), (0, 20)]

    def setUp(self):

        g1 = self.generators[0]
        s1_x_coords = np.random.normal(loc=g1[0], scale=1, size=20)
        s1_y_coords = np.random.normal(loc=g1[1], scale=1, size=20)
        s1_xy_coords = np.zeros((20, 2))
        s1_xy_coords[:, 0] = s1_x_coords
        s1_xy_coords[:, 1] = s1_y_coords

        g2 = self.generators[1]
        s2_x_coords = np.random.normal(loc=g2[0], scale=1, size=20)
        s2_y_coords = np.random.normal(loc=g2[1], scale=1, size=20)
        s2_xy_coords = np.zeros((20, 2))
        s2_xy_coords[:, 0] = s2_x_coords
        s2_xy_coords[:, 1] = s2_y_coords

        g3 = self.generators[2]
        s3_x_coords = np.random.normal(loc=g3[0], scale=1, size=20)
        s3_y_coords = np.random.normal(loc=g3[1], scale=1, size=20)
        s3_xy_coords = np.zeros((20, 2))
        s3_xy_coords[:, 0] = s3_x_coords
        s3_xy_coords[:, 1] = s3_y_coords

        self.all_x_coords = np.concatenate(
            (s1_x_coords, s2_x_coords, s3_x_coords))
        self.all_y_coords = np.concatenate(
            (s1_y_coords, s2_y_coords, s3_y_coords))

        self.traj_lst = [s1_xy_coords, s2_xy_coords, s3_xy_coords]

    def test_predict(self):

        from ..cluster.util import ClusterResult

        centers = np.array(self.generators, dtype='float64')

        result = ClusterResult(
            centers=centers,
            assignments=None,
            distances=None,
            center_indices=None)

        clust = kcenters.KCenters(metric='euclidean', cluster_radius=2)

        clust.result_ = result

        predict_result = clust.predict(np.concatenate(self.traj_lst))

        assert_array_equal(
            predict_result.assignments,
            [0]*20 + [1]*20 + [2]*20)

        assert_true(np.all(predict_result.distances < 4))

        assert_array_equal(
            np.argmin(predict_result.distances[0:20]),
            predict_result.center_indices[0])

        assert_is(predict_result.centers, centers)

    def test_kcenters_hot_start(self):

        clust = kcenters.KCenters(metric='euclidean', cluster_radius=6)

        clust.fit(
            X=np.concatenate(self.traj_lst),
            init_centers=np.array(self.generators[0:2], dtype=float))

        print(clust.result_.center_indices, len(clust.result_.center_indices))

        assert_equal(len(clust.result_.center_indices), 3)
        assert_equal(len(np.unique(clust.result_.center_indices)),
                     np.max(clust.result_.assignments)+1)

        # because two centers were generators, only one center
        # should actually be a frame
        assert_equal(len(np.where(clust.result_.distances == 0)), 1)

    def test_numpy_hybrid(self):
        N_CLUSTERS = 3

        result = hybrid(
            np.concatenate(self.traj_lst),
            distance_method='euclidean',
            n_clusters=N_CLUSTERS,
            dist_cutoff=None,
            n_iters=100,
            random_first_center=False)

        assert len(result.center_indices) == N_CLUSTERS

        centers = util.find_cluster_centers(
            result.assignments, result.distances)
        self.check_generators(
            np.concatenate(self.traj_lst)[centers], distance=4.0)

    def test_numpy_kcenters(self):
        result = kcenters.kcenters(
            np.concatenate(self.traj_lst),
            distance_method='euclidean',
            n_clusters=3,
            dist_cutoff=2,
            init_centers=None,
            random_first_center=False)

        centers = util.find_cluster_centers(
            result.assignments, result.distances)
        self.check_generators(
            np.concatenate(self.traj_lst)[centers], distance=4.0)

    def test_numpy_kmedoids(self):
        N_CLUSTERS = 3

        result = kmedoids.kmedoids(
            np.concatenate(self.traj_lst),
            distance_method='euclidean',
            n_clusters=N_CLUSTERS,
            n_iters=1000)

        assert len(np.unique(result.assignments)) == N_CLUSTERS
        assert len(result.center_indices) == N_CLUSTERS

        centers = util.find_cluster_centers(
            result.assignments, result.distances)
        self.check_generators(
            np.concatenate(self.traj_lst)[centers], distance=4.0)

    def check_generators(self, centers, distance):

        for c in centers:
            mindist = min([np.linalg.norm(c-g) for g in self.generators])
            self.assertLess(
                mindist, distance,
                "Expected center {c} to be less than 2 away frome one of"
                "{g} (was {d}).".
                format(c=c, g=self.generators, d=mindist))

        for g in self.generators:
            mindist = min([np.linalg.norm(c-g) for c in centers])
            self.assertLess(
                mindist, distance,
                "Expected generator {g} to be less than 2 away frome one"
                "of {c} (was {d}).".
                format(c=c, g=self.generators, d=mindist))

@attr('mpi')
def test_kmedoids_propose_center_amongst():

    from ..mpi import MPI
    MPI_RANK = MPI.COMM_WORLD.Get_rank()
    MPI_SIZE = MPI.COMM_WORLD.Get_size()

    a = np.arange(17)
    X = a[MPI_RANK::MPI_SIZE]
    assignments = (X % 3 == 0).astype('int')

    state_inds = np.where(assignments == 1)[0]

    prop_c, (rank, local_ind) = kmedoids._propose_new_center_amongst(
        X, state_inds, mpi_mode=True, random_state=0)

    assert_equal(prop_c % 3, 0)
    assert_equal(a[rank::MPI_SIZE][local_ind], prop_c)


@attr('mpi')
def test_kmedoids_propose_center_amongst_hits_all():

    from ..mpi import MPI
    MPI_RANK = MPI.COMM_WORLD.Get_rank()
    MPI_SIZE = MPI.COMM_WORLD.Get_size()

    a = np.arange(17)
    X = a[MPI_RANK::MPI_SIZE]
    assignments = (X % 3 == 0).astype('int')

    state_inds = np.where(assignments == 1)[0]

    hits = set()
    for i in range(100):
        prop_c, (rank, local_ind) = kmedoids._propose_new_center_amongst(
            X, state_inds, mpi_mode=True, random_state=i)

        assert_equal(prop_c % 3, 0)
        assert_equal(a[rank::MPI_SIZE][local_ind], prop_c)
        hits.add(int(prop_c))

    assert_equal(hits, set([0, 3, 6, 9, 12, 15]))


if __name__ == '__main__':
    unittest.main()

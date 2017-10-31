from nose.tools import assert_equal, assert_raises
from numpy.testing import (assert_array_equal, assert_allclose,
                           assert_almost_equal)

import numpy as np

from enspara import exception

from enspara.util import array as ra
from enspara.info_theory import mutual_info


# GENERATORS FOR BUILDING ARRAYS

def zero_mi_np():
    n_trjs = 3
    n_frames = 10000
    n_features = 5

    data = np.random.randint(1, 5, (n_trjs, n_frames, n_features))
    n_states = [5] * n_features

    return data, n_states


def nonzero_mi_np():
    a, n_states = zero_mi_np()
    a[:, :, -2] = a[:, :, -1]
    return a, n_states


def zero_mi_ra():
    data, n_states = zero_mi_np()
    a = ra.RaggedArray(array=data[0], lengths=[1000, 2000, 5000, 2000])
    return a, n_states


def zero_mi_list():
    a, n_states = zero_mi_ra()
    l = [row for row in a]
    return l, n_states


def nonzero_mi_ra():
    data, n_states = nonzero_mi_np()
    a = ra.RaggedArray(array=data[0], lengths=[1000, 2000, 5000, 2000])
    return a, n_states


def nonzero_mi_list():
    a, n_states = nonzero_mi_ra()
    l = [row for row in a]
    return l, n_states


# ACTUAL TESTS

def test_mi_to_apc():

    mi = np.array([[1.0, 0.5, 0.1],
                   [0.5, 0.7, 0.1],
                   [0.1, 0.1, 0.7]])

    apc = mutual_info.mi_to_apc(mi)
    expected_apc = np.array(
        [[0.1400, 0.0955, 0.0244],
         [0.0955, 0.0833, 0.0211],
         [0.0244, 0.0211, 0.0566]])

    assert_almost_equal(apc, expected_apc, decimal=4)


def test_check_feature_size():

    states_same = [
        np.array([[0, 0, 0],
                  [0, 0, 0]]),
        np.array([[0, 0, 0],
                  [0, 0, 0]])]

    mutual_info.check_features_states(states_same, [2, 2, 2])

    with assert_raises(exception.DataInvalid):
        mutual_info.check_features_states(states_same, [2, 2])

    states_different = [
        np.array([[0, 0, 0],
                  [0, 0, 0]]),
        np.array([[0, 0, 0]])]

    mutual_info.check_features_states(states_different, [2, 2, 2])

    states_different_features = [
        np.array([[0, 0],
                  [0, 0]]),
        np.array([[0, 0, 0],
                  [0, 0, 0]])]

    with assert_raises(exception.DataInvalid):
        mutual_info.check_features_states(states_different_features, [3])


def test_symmetrical_mi_zero():

    zero_mi_funcs = [zero_mi_np, zero_mi_ra, zero_mi_list]

    for a, n_states in (f() for f in zero_mi_funcs):
        mi = mutual_info.mi_matrix(a, a, n_states, n_states)

        assert_allclose(np.diag(mi), 1.723, atol=0.1)
        mi[np.diag_indices_from(mi)] = 0

        assert_allclose(mi, 0, atol=1e-3)


def test_asymmetrical_mi_zero():

    zero_mi_funcs = [zero_mi_np, zero_mi_ra, zero_mi_list]

    for gen_f in zero_mi_funcs:
        a, n_a = gen_f()
        b, n_b = gen_f()

        mi = mutual_info.mi_matrix(a, b, n_a, n_b)
        assert_allclose(np.diag(mi), 0, atol=0.1)
        mi[np.diag_indices_from(mi)] = 0

        assert_allclose(mi, 0, atol=1e-3)


def test_symmetrical_mi_nonzero():
    # test that the MI matrix for sets of uncorrelated things results
    # in zero MI

    nonzero_mi_funcs = [nonzero_mi_np, nonzero_mi_ra, nonzero_mi_list]
    for a, n_states in (f() for f in nonzero_mi_funcs):

        mi = mutual_info.mi_matrix(a, a, n_states, n_states)

        print(mi.shape)

        assert_almost_equal(mi[-1, -2], 0.86114, decimal=3)
        mi[-1, -2] = mi[-2, -1] = 0

        assert_almost_equal(np.diag(mi), 1.722, decimal=2)
        mi[np.diag_indices_from(mi)] = 0

        assert_allclose(mi, 0, atol=1e-3)


def test_asymmetrical_mi_nonzero():
    # test that the MI matrix for sets of uncorrelated things results
    # in zero MI, but on asymmetrical data, i.e. a[i] != b[i]

    zero_mi_funcs = [zero_mi_np, zero_mi_ra, zero_mi_list]

    for gen_f in zero_mi_funcs:
        print('checking', gen_f.__name__)

        a, n_a = gen_f()
        b, n_b = gen_f()

        for r_a, r_b in zip(a, b):
            r_a[:, 0] = r_b[:, 3]

        mi = mutual_info.mi_matrix(a, b, n_a, n_b)

        assert_almost_equal(mi[0, 3], 0.86114, decimal=3)
        mi[3, 0] = mi[0, 3] = 0

        assert_allclose(mi, 0, atol=1e-2)


def test_joint_count_binning():

    trj1 = np.array([1]*3 + [2]*6 + [1]*6)
    trj2 = np.array([1]*9 + [0]*3 + [2]*3)

    expected_jc = np.array([[0, 0, 0],
                            [3, 3, 3],
                            [0, 6, 0]])

    jc = mutual_info.joint_counts(trj1, trj2)
    assert_equal(jc.dtype, 'int')
    assert_array_equal(jc, expected_jc)

    jc = mutual_info.joint_counts(trj1, trj2, 3, 3)
    assert_equal(jc.dtype, 'int')
    assert_array_equal(jc, expected_jc)


def test_symmetrical_apc_zero():
    # test that the APC matrix for sets of uncorrelated things results
    # in zero APC
    zero_mi_funcs = [zero_mi_np, zero_mi_ra, zero_mi_list]

    for a, n_states in (f() for f in zero_mi_funcs):
        apc = mutual_info.apc_matrix(a, a, n_states, n_states)

        assert_allclose(np.diag(apc), 0, atol=0.2)
        apc[np.diag_indices_from(apc)] = 0

        assert_allclose(apc, 0, atol=1e-3)


def test_asymmetrical_apc_zero():
    # test that the APC matrix for sets of uncorrelated things results
    # in zero APC, but on asymmetrical data, i.e. a[i] != b[i]

    zero_mi_funcs = [zero_mi_np, zero_mi_ra, zero_mi_list]

    for gen_f in zero_mi_funcs:
        a, n_a = gen_f()
        b, n_b = gen_f()

        apc = mutual_info.apc_matrix(a, b, n_a, n_b)

        assert_allclose(np.diag(apc), 0, atol=0.1)
        apc[np.diag_indices_from(apc)] = 0

        assert_allclose(apc, 0, atol=1e-3)


def test_apc_nonzero():
    # test that the MI matrix for sets of uncorrelated things results
    # in zero MI

    nonzero_mi_funcs = [nonzero_mi_np, nonzero_mi_ra, nonzero_mi_list]
    for a, n_states in (f() for f in nonzero_mi_funcs):

        apc = mutual_info.apc_matrix(a, a, n_states, n_states)

        # nonzero APC gives rise to higher self-correlations?
        assert_almost_equal(apc[-1, -1], 2.96752422e-02, decimal=3)
        assert_almost_equal(apc[-2, -2], 2.96752422e-02, decimal=3)
        apc[-2, -2] = apc[-1, -1] = 0

        assert_allclose(apc, 0, atol=1e-3)


def test_nmi_apc_zero():
    # test that the APC matrix for sets of uncorrelated things results
    # in zero APC
    zero_mi_funcs = [zero_mi_np, zero_mi_ra, zero_mi_list]

    for a, n_states in (f() for f in zero_mi_funcs):
        nmi_apc = mutual_info.nmi_apc_matrix(a, n_states)

        assert_allclose(np.diag(nmi_apc), -np.inf, atol=0.001)
        nmi_apc[np.diag_indices_from(nmi_apc)] = 1

        assert_allclose(nmi_apc, 1, atol=1e-3)


def test_nmi_apc_nonzero():
    # test that the MI matrix for sets of uncorrelated things results
    # in zero MI

    nonzero_mi_funcs = [nonzero_mi_np, nonzero_mi_ra, nonzero_mi_list]
    for a, n_states in (f() for f in nonzero_mi_funcs):

        nmi_apc = mutual_info.nmi_apc_matrix(a, n_states)

        assert_allclose(np.diag(nmi_apc), -np.inf)
        nmi_apc[np.diag_indices_from(nmi_apc)] = 1

        assert_equal(nmi_apc[-1, -1], 1)
        assert_equal(nmi_apc[-2, -2], 1)

        assert_allclose(nmi_apc, 1, atol=1e-1)


def test_network_deconvolution():
    from numpy.linalg import matrix_power

    G_dir = np.array([[0.5, 0.4, 0.1],
                      [0.2, 0.7, 0.1],
                      [0.1, 0.2, 0.7]])

    # prepare G_obs by computing the transitive closure
    G_obs = G_dir.copy()
    for i in range(2, 1000):
        G_obs += matrix_power(G_dir, i)

    G_dir_computed = mutual_info.deconvolute_network(G_obs)

    assert_allclose(G_dir, G_dir_computed, atol=1e-3)
from nose.tools import assert_equal
from numpy.testing import assert_array_equal, assert_allclose

import numpy as np
import scipy.sparse

from .transition_matrices import counts_to_probs, assigns_to_counts, \
    eigenspectra
from .timescales import implied_timescales


# array types we want to guarantee support for
ARR_TYPES = [
    np.array, scipy.sparse.lil_matrix, scipy.sparse.csr_matrix,
    scipy.sparse.coo_matrix, scipy.sparse.csc_matrix,
    scipy.sparse.dia_matrix, scipy.sparse.dok_matrix
]


def test_implied_timescales():

    in_assigns = np.array(
        [ ([0]*30 + [1]*20 + [-1]*10),
          ([2]*20 + [-1]*5 + [1]*35),
          ([0]*10 + [1]*30 + [2]*20),
          ])

    tscales = implied_timescales(in_assigns, lag_times=range(1, 5))
    expected = np.array(
        [[1., 26.029585],
         [2., 24.852135],
         [3., 23.666594],
         [4., 22.471671]])

    assert_allclose(tscales, expected, rtol=1e-03)

    tscales = implied_timescales(
        in_assigns, lag_times=range(1, 5), symmetrization='transpose')
    expected = np.array(
        [[1., 38.497835],
         [2., 36.990989],
         [3., 35.478863],
         [4., 33.960748]])

    assert_allclose(tscales, expected, rtol=1e-03)


def test_eigenspectra_types():

    expected_vals = np.array([ 1., 0.56457513, 0.03542487])
    expected_vecs = np.array(
        [[ 0.33333333,  0.8051731 , -0.13550992],
         [ 0.33333333, -0.51994159, -0.6295454 ],
         [ 0.33333333, -0.28523152,  0.76505532]])

    for arr_type in ARR_TYPES:
        probs = arr_type(
            [[0.7, 0.1, 0.2],
             [0.1, 0.5, 0.4],
             [0.2, 0.4, 0.4]])

        try:
            e_vals, e_vecs = eigenspectra(probs)
        except ValueError:
            print("Failed on type %s" % arr_type)
            raise

        assert_allclose(e_vecs, expected_vecs)
        assert_allclose(e_vals, expected_vals)


def test_assigns_to_counts_negnums():
    '''counts_to_probs ignores -1 values
    '''

    in_m = np.array(
            [[0, 2,  0, -1],
             [1, 2, -1, -1],
             [1, 0,  0, 1]])

    counts = assigns_to_counts(in_m)

    expected = np.array([[1, 1, 1],
                         [1, 0, 1],
                         [1, 0, 0]])

    assert_array_equal(counts.toarray(), expected)


def test_counts_to_probs_types():
    '''counts_to_probs accepts & returns ndarrays, spmatrix subclasses.
    '''

    for arr_type in ARR_TYPES:

        in_m = arr_type(
            [[0, 2, 8],
             [4, 2, 4],
             [7, 3, 0]])
        out_m = counts_to_probs(in_m)

        assert_equal(type(in_m), type(out_m))

        # cast to ndarray if necessary for comparison to correct result
        try:
            out_m = out_m.toarray()
        except AttributeError:
            pass

        out_m = np.round(out_m, decimals=1)

        expected = np.array(
            [[0,   0.2, 0.8],
             [0.4, 0.2, 0.4],
             [0.7, 0.3, 0]])

        assert_array_equal(
            out_m,
            expected)
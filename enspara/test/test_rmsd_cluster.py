import os
import tempfile
import hashlib
import shutil

from datetime import datetime

from mdtraj.testing import get_fn

from nose.tools import assert_equal, assert_raises

import numpy as np
from numpy.testing import assert_array_equal

from .. import exception
from ..util import array as ra

from ..apps import rmsd_cluster

TEST_DIR = os.path.dirname(__file__)


def runhelper(args, expected_size, algorithm='khybrid', expected_k=None,
              expect_reassignment=True):

    td = tempfile.mkdtemp(dir=os.getcwd())
    tf = hashlib.md5(str(datetime.now().timestamp())
                     .encode('utf-8')).hexdigest()[0:8]
    base = os.path.join(td, tf)

    fnames = {
        'distances': base+'distances.h5',
        'assignments': base+'assignments.h5',
        'centers': base+'centers.pkl',
    }

    try:
        rmsd_cluster.main([
            '',  # req'd because arg[0] is expected to be program name
            '--distances', fnames['distances'],
            '--centers', fnames['centers'],
            '--assignments', fnames['assignments']] + args)

        if expect_reassignment:
            assert os.path.isfile(fnames['assignments']), \
                "Couldn't find %s. Dir contained: %s" % (
                    fnames['assignments'],
                    os.listdir(os.path.dirname(fnames['assignments'])))

            assigns = ra.load(fnames['assignments'])
            if type(assigns) is ra.RaggedArray:
                assert_equal(len(assigns), expected_size[0])
                assert_equal(assigns._data.dtype, np.int)
                assert_array_equal(assigns.lengths, expected_size[1])
                if expected_k is not None:
                    assert_array_equal(
                        np.unique(assigns._data),
                        np.arange(expected_k))
            else:
                assert_equal(assigns.shape, expected_size)
                assert_equal(assigns.dtype, np.int)
                if expected_k is not None:
                    assert_array_equal(
                        np.unique(assigns),
                        np.arange(expected_k))

            distfile = fnames['distances']
            assert os.path.isfile(distfile), \
                "Couldn't find %s. Dir contained: %s" % (
                distfile, os.listdir(os.path.dirname(distfile)))
        else:
            assert not os.path.isfile(fnames['assignments'])
            assert not os.path.isfile(fnames['distances'])

        ctrsfile = fnames['centers']
        assert os.path.isfile(ctrsfile), \
            "Couldn't find %s. Dir contained: %s" % (
            ctrsfile, os.listdir(os.path.dirname(ctrsfile)))

    finally:
        shutil.rmtree(td)
        pass


def test_rmsd_cluster_basic():

    expected_size = (2, 501)

    runhelper([
        '--trajectories', get_fn('frame0.xtc'), get_fn('frame0.xtc'),
        '--topology', get_fn('native.pdb'),
        '--rmsd-cutoff', '0.1',
        '--atoms', '(name N or name C or name CA or name H or name O)',
        '--algorithm', 'khybrid'],
        expected_size=expected_size)


def test_rmsd_cluster_basic_kcenters():

    expected_size = (2, 501)

    runhelper([
        '--trajectories', get_fn('frame0.xtc'), get_fn('frame0.xtc'),
        '--topology', get_fn('native.pdb'),
        '--rmsd-cutoff', '0.1',
        '--atoms', '(name N or name C or name CA or name H or name O)',
        '--algorithm', 'kcenters'],
        expected_size=expected_size,
        algorithm='kcenters')


def test_rmsd_cluster_fixed_k_kcenters():

    expected_size = (2, 501)

    expected_k = 10

    runhelper([
        '--trajectories', get_fn('frame0.xtc'), get_fn('frame0.xtc'),
        '--topology', get_fn('native.pdb'),
        '--n-clusters', str(expected_k),
        '--atoms', '(name N or name C or name CA or name H or name O)',
        '--algorithm', 'kcenters'],
        expected_size=expected_size,
        algorithm='kcenters',
        expected_k=expected_k)


def test_rmsd_cluster_broken_atoms():

    expected_size = (2, 501)

    with assert_raises(exception.ImproperlyConfigured):
        runhelper([
            '--trajectories', get_fn('frame0.xtc'), get_fn('frame0.xtc'),
            '--topology', get_fn('native.pdb'),
            '--rmsd-cutoff', '0.1',
            '--atoms', 'residue -1',
            '--algorithm', 'khybrid'],
            expected_size=expected_size)


def test_rmsd_cluster_selection():

    expected_size = (2, 501)

    runhelper([
        '--trajectories', get_fn('frame0.xtc'), get_fn('frame0.xtc'),
        '--topology', get_fn('native.pdb'),
        '--rmsd-cutoff', '0.1',
        '--atoms', '(name N or name C or name CA)',
        '--algorithm', 'khybrid'],
        expected_size=expected_size)


def test_rmsd_cluster_subsample():

    expected_size = (2, 501)

    runhelper([
        '--trajectories', get_fn('frame0.xtc'), get_fn('frame0.xtc'),
        '--topology', get_fn('native.pdb'),
        '--rmsd-cutoff', '0.1',
        '--subsample', '4',
        '--atoms', '(name N or name C or name CA or name H or name O)',
        '--algorithm', 'khybrid'],
        expected_size=expected_size)


def test_rmsd_cluster_multiprocess():

    expected_size = (2, 501)

    runhelper([
        '--trajectories', get_fn('frame0.xtc'), get_fn('frame0.xtc'),
        '--topology', get_fn('native.pdb'),
        '--rmsd-cutoff', '0.1',
        '--processes', '4',
        '--atoms', '(name N or name C or name CA or name H or name O)',
        '--algorithm', 'khybrid'],
        expected_size=expected_size)


def test_rmsd_cluster_subsample_and_noreassign():

    expected_size = (2, 501)

    runhelper([
        '--trajectories', get_fn('frame0.xtc'), get_fn('frame0.xtc'),
        '--topology', get_fn('native.pdb'),
        '--atoms', '(name N or name C or name CA or name H or name O)',
        '--rmsd-cutoff', '0.1',
        '--algorithm', 'khybrid',
        '--processes', '4',
        '--subsample', '4',
        '--no-reassign'],
        expect_reassignment=False,
        expected_size=expected_size)


def test_rmsd_cluster_multitop():

    expected_size = (3, (501, 501, 5001))

    # trj is length 5001
    xtc2 = os.path.join(TEST_DIR, 'cards_data', 'trj0.xtc')
    top2 = os.path.join(TEST_DIR, 'cards_data', 'PROT_only.pdb')

    runhelper([
        '--trajectories', get_fn('frame0.xtc'), get_fn('frame0.xtc'),
        '--trajectories', xtc2,
        '--topology', get_fn('native.pdb'),
        '--topology', top2,
        '--atoms', '(name N or name C or name CA or name H or name O) '
                   'and (residue 2)',
        '--rmsd-cutoff', '0.1',
        '--algorithm', 'khybrid'],
        expected_size=expected_size)


def test_rmsd_cluster_multitop_multiselection():

    expected_size = (3, (501, 501, 5001))

    xtc2 = os.path.join(TEST_DIR, 'cards_data', 'trj0.xtc')
    top2 = os.path.join(TEST_DIR, 'cards_data', 'PROT_only.pdb')

    runhelper([
        '--trajectories', get_fn('frame0.xtc'), get_fn('frame0.xtc'),
        '--topology', get_fn('native.pdb'),
        '--atoms', '(name N or name O) and (residue 2)',
        '--trajectories', xtc2,
        '--topology', top2,
        '--atoms', '(name CA) and (residue 3 or residue 4)',
        '--rmsd-cutoff', '0.1',
        '--algorithm', 'khybrid',
        '--subsample', '4'],
        expected_size=expected_size)

    # reverse the order. This will catch some cases where the first
    # selection works on both.
    runhelper([
        '--trajectories', xtc2,
        '--topology', top2,
        '--atoms', '(name CA) and (residue 3 or residue 4)',
        '--trajectories', get_fn('frame0.xtc'), get_fn('frame0.xtc'),
        '--topology', get_fn('native.pdb'),
        '--atoms', '(name N or name O) and (residue 2)',
        '--rmsd-cutoff', '0.1',
        '--algorithm', 'khybrid',
        '--subsample', '4'],
        expected_size=(expected_size[0], expected_size[1][::-1]))


def test_rmsd_cluster_multitop_multiselection_noreassign():

    expected_size = (3, (501, 501, 5001))

    xtc2 = os.path.join(TEST_DIR, 'cards_data', 'trj0.xtc')
    top2 = os.path.join(TEST_DIR, 'cards_data', 'PROT_only.pdb')

    runhelper([
        '--trajectories', get_fn('frame0.xtc'), get_fn('frame0.xtc'),
        '--topology', get_fn('native.pdb'),
        '--atoms', '(name N or name O) and (residue 2)',
        '--trajectories', xtc2,
        '--topology', top2,
        '--atoms', '(name CA) and (residue 3 or residue 4)',
        '--rmsd-cutoff', '0.1',
        '--algorithm', 'khybrid',
        '--subsample', '4',
        '--no-reassign'],
        expected_size=expected_size,
        expect_reassignment=False)

    # reverse the order. This will catch some cases where the first
    # selection works on both.
    runhelper([
        '--trajectories', xtc2,
        '--topology', top2,
        '--atoms', '(name CA) and (residue 3 or residue 4)',
        '--trajectories', get_fn('frame0.xtc'), get_fn('frame0.xtc'),
        '--topology', get_fn('native.pdb'),
        '--atoms', '(name N or name O) and (residue 2)',
        '--rmsd-cutoff', '0.1',
        '--algorithm', 'khybrid',
        '--subsample', '4',
        '--no-reassign'],
        expect_reassignment=False,
        expected_size=(expected_size[0], expected_size[1][::-1]))

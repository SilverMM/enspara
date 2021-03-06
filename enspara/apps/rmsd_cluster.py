"""The RMSD Cluster App allows you to cluster your trajectories based on root
mean square deviation. The entire protein or specific residue locations can be
used for the clustering. Parameters such as the clustering algorithm and
cluster radius can be specified. The app will return information about cluster
centers and frame assignments. See the apps tab for more information.
"""

import sys
import argparse
import os
import logging
import itertools
import pickle
import json
import warnings
import time

from multiprocessing import cpu_count

import mdtraj as md

logging.basicConfig(
    level=logging.INFO,
    format=('%(asctime)s %(name)-8s %(levelname)-7s %(message)s'),
    datefmt='%m-%d-%Y %H:%M:%S')

from enspara.apps.reassign import reassign
from enspara.apps.util import readable_dir

from enspara.cluster import KHybrid, KCenters
from enspara.util import array as ra
from enspara.util import load_as_concatenated
from enspara.util.log import timed
from enspara.cluster.util import load_frames
from enspara import exception


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def process_command_line(argv):
    '''Parse the command line and do a first-pass on processing them into a
    format appropriate for the rest of the script.'''

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
        description="Cluster a set (or several sets) of trajectories "
                    "into a single state space based upon RMSD.")

    # INPUTS
    parser.add_argument(
        '--trajectories', required=True, nargs="+", action='append',
        help="List of paths to aligned trajectory files to cluster. "
             "All file types that MDTraj supports are supported here.")
    parser.add_argument(
        '--topology', required=True, action='append', dest='topologies',
        help="The topology file for the trajectories. This flag must be"
             " specified once for each instance of the --trajectories "
             "flag. The first --topology flag is taken to be the "
             "topology to use for the first instance of the "
             "--trajectories flag, and so forth.")

    # PARAMETERS
    parser.add_argument(
        '--algorithm', required=True, choices=["khybrid", "kcenters"],
        help="The clustering algorithm to use.")
    parser.add_argument(
        '--atoms', action="append", required=True,
        help="The atoms from the trajectories (using MDTraj "
             "atom-selection syntax) to cluster based upon. Specify "
             "once to apply this selection to every set of "
             "trajectories specified by the --trajectories flag, or "
             "once for each different topology (i.e. the number of "
             "times --trajectories and --topology was specified.)")
    parser.add_argument(
        '--rmsd-cutoff', default=None, type=float,
        help="Produce clusters with a maximum distance to cluster "
             "center of this value.. Units: nm.")
    parser.add_argument(
        '--n-clusters', default=None, type=int,
        help="Produce at least this number of clusters.")
    parser.add_argument(
        '--processes', default=cpu_count(), type=int,
        help="Number processes to use for loading and clustering.")
    parser.add_argument(
        '--subsample', default=None, type=int,
        help="Take only every nth frame when loading trajectories. "
             "1 implies no subsampling.")
    parser.add_argument(
        '--no-reassign', default=False, action='store_true',
        help="Do not do a reassigment step. Ignored if --subsample is "
             "not supplied or 1.")

    # OUTPUT
    parser.add_argument(
        '--distances', required=True, action=readable_dir,
        help="The location to write the distances file.")
    parser.add_argument(
        '--centers', required=True, action=readable_dir,
        help="The location to write the cluster center structures.")
    parser.add_argument(
        '--assignments', required=True, action=readable_dir,
        help="The location to write assignments of frames to clusters.")

    args = parser.parse_args(argv[1:])

    if args.rmsd_cutoff is None and args.n_clusters is None:
        raise exception.ImproperlyConfigured(
            "At least one of --rmsd-cutoff and --n-clusters is "
            "required to cluster.")

    if len(args.atoms) == 1:
        args.atoms = args.atoms * len(args.trajectories)
    elif len(args.atoms) != len(args.trajectories):
        raise exception.ImproperlyConfigured(
            "Flag --atoms must be provided either once (selection is "
            "applied to all trajectories) or the same number of times "
            "--trajectories is supplied.")

    if len(args.topologies) != len(args.trajectories):
        raise exception.ImproperlyConfigured(
            "The number of --topology and --trajectory flags must agree.")

    if args.algorithm == 'kcenters':
        args.Clusterer = KCenters
    elif args.algorithm == 'khybrid':
        args.Clusterer = KHybrid

    if args.subsample is None:
        args.subsample = 1

    if args.no_reassign and args.subsample == 1:
        warnings.warn("When subsampling is 1 (or unspecified), --no-reassign has no effect.")

    if args.centers[args.centers.rfind('.'):] == '.h5':
        warnings.warn(
            "You provided a centers file that looks like it's an h5... "
            "centers are saved as pickle. Are you sure this is what you want?")

    return args


def load(topologies, trajectories, selections, stride, processes):

    for top, selection in zip(topologies, selections):
        sentinel_trj = md.load(top)
        try:
            # noop, but causes fast-fail w/bad args.atoms
            sentinel_trj.top.select(selection)
        except:
            raise exception.ImproperlyConfigured((
                "The provided selection '{s}' didn't match the topology "
                "file, {t}").format(s=selection, t=top))

    flat_trjs = []
    configs = []
    n_inds = None

    for topfile, trjset, selection in zip(topologies, trajectories,
                                          selections):
        top = md.load(topfile).top
        indices = top.select(selection)

        if n_inds is not None:
            if n_inds != len(indices):
                raise exception.ImproperlyConfigured(
                    ("Selection on topology %s selected %s atoms, but "
                     "other selections selected %s atoms.") %
                    (topfile, len(indices), n_inds))
        n_inds = len(indices)

        for trj in trjset:
            flat_trjs.append(trj)
            configs.append({
                'top': top,
                'stride': stride,
                'atom_indices': indices,
                })

    logger.info(
        "Loading %s trajectories with %s atoms using %s processes "
        "(subsampling %s)",
        len(flat_trjs), len(top.select(selection)), processes, stride)
    assert len(top.select(selection)) > 0, "No atoms selected for clustering"

    with timed("Loading took %.1f sec", logger.info):
        lengths, xyz = load_as_concatenated(
            flat_trjs, args=configs, processes=processes)

    with timed("Turned over array in %.2f min", logging.info):
        tmp_xyz = xyz.copy()
        del xyz
        xyz = tmp_xyz

    logger.info(
        "Loaded %s frames.", len(xyz))

    return lengths, xyz, top.subset(top.select(selection))


def load_asymm_frames(center_indices, trajectories, topology, subsample):

    frames = []
    begin_index = 0
    for topfile, trjset in zip(topology, trajectories):
        end_index = begin_index + len(trjset)
        target_centers = [c for c in center_indices
                          if begin_index <= c[0] < end_index]

        try:
            subframes = load_frames(
                list(itertools.chain(*trajectories)),
                target_centers,
                top=md.load(topfile).top,
                stride=subsample)
        except exception.ImproperlyConfigured:
            logger.error('Failure to load cluster centers %s for topology %s',
                         topfile, target_centers)
            raise

        frames.extend(subframes)
        begin_index += len(trjset)

    return frames


def main(argv=None):
    '''Run the driver script for this module. This code only runs if we're
    being run as a script. Otherwise, it's silent and just exposes methods.'''
    args = process_command_line(argv)

    targets = {os.path.basename(topf): "%s xtcs" % len(trjfs) for topf, trjfs
               in zip(args.topologies, args.trajectories)}
    logger.info("Beginning RMSD Clustering app. Operating on targets:\n%s",
                json.dumps(targets, indent=4))

    tick = time.perf_counter()
    lengths, xyz, select_top = load(
        args.topologies, args.trajectories, selections=args.atoms,
        stride=args.subsample, processes=args.processes)

    logger.info(
        "Loading finished in %.1f s. Clustering using %s atoms matching '%s'.",
        round(time.perf_counter() - tick, 2), xyz.shape[1], args.atoms)

    clustering = args.Clusterer(
        metric=md.rmsd,
        n_clusters=args.n_clusters,
        cluster_radius=args.rmsd_cutoff)

    # md.rmsd requires an md.Trajectory object, so wrap `xyz` in
    # the topology.
    clustering.fit(md.Trajectory(xyz=xyz, topology=select_top))

    logger.info(
        "Clustered %s frames into %s clusters in %s seconds.",
        sum(lengths), len(clustering.centers_), clustering.runtime_)

    result = clustering.result_.partition(lengths)

    outdir = os.path.dirname(args.centers)
    logger.info("Saving cluster centers at %s", outdir)

    try:
        os.makedirs(outdir)
    except FileExistsError:
        pass

    centers = load_asymm_frames(result.center_indices, args.trajectories,
                                args.topologies, args.subsample)
    with open(args.centers, 'wb') as f:
        pickle.dump(centers, f)

    if args.subsample == 1:
        logger.debug("Subsampling was 1, not reassigning.")
        ra.save(args.distances, result.distances)
        ra.save(args.assignments, result.assignments)
    if not args.no_reassign:
        logger.debug("Reassigning data from subsampling of %s", args.subsample)
        # overwrite temporary output with actual results
        assig, dist = reassign(
            args.topologies, args.trajectories, args.atoms,
            centers=result.centers)

        ra.save(args.distances, dist)
        ra.save(args.assignments, assig)
    else:
        logger.debug("Got --no-reassign, not doing reassigment")

    logger.info("Success! Data can be found in %s.",
                os.path.dirname(args.distances))

    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))

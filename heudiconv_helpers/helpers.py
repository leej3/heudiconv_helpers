from collections import deque, OrderedDict
import numpy as np
from pathlib import Path
import pandas as pd
import json
import platform
import os
import datetime
import os.path as op
from collections import namedtuple, Iterable
from heudiconv_helpers import helpers as hh
import sys
import shutil
import subprocess
from importlib import reload
__version__ = "helpers:0.0.6"
print(__version__)


def coerce_to_int(num, name):
    if np.isclose(num, int(num)):
        num = int(num)
    else:
        raise ValueError("%s must be an integer or a rounded float" % name)
    return num


def gen_slice_timings(tr, nslices, nvolumes=1, pattern='alt+z'):
    """Generate slice timings for all slices collected in some number of volumes.

    Parameters
    ----------
    tr: float
        Repitition Time in same units as desired for output
    nslices: int, float
        Number of slices collected in each tr
    nvolumes: int, float  optional
        Number of volumes you would like slice timings for
    pattern: string, one of ('altplus', 'alt+z', 'alt+z2', 'altminus', 'alt-z',
                             'alt-z2', 'seq+z', 'seqplus', 'seq-z', seqminus')
        The slice sampling pattern, names are taken from AFNI nomenclature

    Returns
    -------
    output: list of floats or np.nan
        List of floats for slice timing in same units as tr.
        np.nan is returned if any of the arguments are nan.
    """
    if any(np.isnan([tr, nslices, nvolumes])):
        return np.nan
    tr = coerce_to_int(tr, "tr")
    nslices = coerce_to_int(nslices, "nslices")
    nvolumes = coerce_to_int(nvolumes, "nvolumes")

    ordered_times = [tt for tt in np.linspace(0, tr, nslices + 1)][:-1]
    middle = int((nslices % 2) + len(ordered_times) / 2)
    first_half = ordered_times[:middle]
    second_half = ordered_times[middle:]

    if pattern == 'altplus' or pattern == 'alt+z':
        tr_timings = np.zeros(nslices)
        tr_timings[::2] = first_half
        tr_timings[1::2] = second_half
    elif pattern == 'alt+z2':
        tr_timings = np.zeros(nslices)
        tr_timings[::2] = first_half
        tr_timings[1::2] = second_half
        tr_timings = deque(tr_timings)
        tr_timings.rotate(1)
        tr_timings = np.array(tr_timings)
    elif pattern == 'altminus' or pattern == 'alt-z':
        tr_timings = np.zeros(nslices)
        tr_timings[::2] = first_half
        tr_timings[1::2] = second_half
        tr_timings = tr_timings[::-1]
    elif pattern == 'alt-z2':
        tr_timings = np.zeros(nslices)
        tr_timings[::2] = first_half
        tr_timings[1::2] = second_half
        tr_timings = deque(tr_timings)
        tr_timings.rotate(1)
        tr_timings = np.array(tr_timings)[::-1]
    elif pattern == 'seq+z' or pattern == 'seqplus':
        tr_timings = ordered_times
    elif pattern == 'seq-z' or pattern == 'seqminus':
        tr_timings = ordered_times[::-1]
    else:
        raise NotImplementedError(
            'Pattern %s is not implemented yet' % pattern)

    output = np.hstack([np.array(tr_timings) + n for n in range(nvolumes)])
    output = list(float(str(np.round(oo, 6))) for oo in output)
    return output


def write_json(path, data):
    path = Path(path)
    path.write_text(json.dumps(data, indent=0))


def _get_fields(row, data, fieldnames):
    for f_idx, field in enumerate(fieldnames):
        tmp = data
        if isinstance(field, tuple):

            for ii, key in enumerate(field):
                try:
                    if ii == (len(field) - 1):
                        # tmp[key] = values_to_set[f_idx]
                        row = row.append(
                            pd.Series({'__'.join(field): tmp[key]}))
                    else:
                        tmp[key]
                        tmp = tmp[key]
                except KeyError:
                    row = row.append(pd.Series({'__'.join(field): np.nan}))
        else:
            try:
                row = row.append(pd.Series({field: data[field]}))
            except KeyError:
                row = row.append(pd.Series({field: np.nan}))

    return row


def _set_fields(data, fieldnames, values_to_set):
    if not isinstance(values_to_set, list):
        raise ValueError('values_to_set" argument must be a list')
    for f_idx, field in enumerate(fieldnames):
        tmp = data
        if isinstance(field, tuple):

            for ii, key in enumerate(field):
                try:
                    if ii == (len(field) - 1):
                        tmp[key] = values_to_set[f_idx]
                    else:
                        tmp[key]
                        tmp = tmp[key]
                except KeyError:
                    pass
        else:
            data[field] = values_to_set[f_idx]

    return data


def _del_fields(j_in, fieldnames):
    """
    Remove fields from json data inplace.
    Each field name should be  a tuple.
    """
    for field in fieldnames:
        tmp = j_in
        if isinstance(field, tuple):
            for i, l in enumerate(field):
                try:
                    if i == (len(field) - 1):
                        del tmp[l]
                    else:
                        tmp[l]
                        tmp = tmp[l]
                except KeyError:
                    pass
#                         print(f, ' not found as a json field')
        else:
            try:
                del tmp[field]
            except KeyError:
                pass
#                         print(f, ' not found as a json field')


def json_action(row, json_col='json_path', fieldnames=None,
                action='get', values_to_set=None):
    """
    For mapping operations with json files across dataframe rows.

    Parameters
    ----------
    row: pd.Series
        Dataframe row containing a column that has a path to a json.
    json_col: string
        Name of Dataframe column that contains the path to an appropriate json
    fieldnames: tuple,str or a list of either/both
       One or more json fieldnames to perform an action with. Nested
        fieldnames should be expressed as a tuple of strings.
    action: string, one of ('get', 'set', 'delete')
        'get' will return an updated row with the retrieved fieldnames. 'set'
    will write to the provided fieldnames in the json file. 'delete' removes
    the provided fieldnames from the json file.
    values_to_set: str,iterable
        Must match fieldnames in number. Can only be used when action is 'set'.

     Returns
    -------
    row: for get the returned row will be modified

    Examples
    -------
    df.apply(lambda row: json_action(row,
                         fieldnames = ['SliceTiming',
                         ('primary_field',
                         'AcquisitionTime')],
                         action = 'set',
                         values_to_set = [[0,0.2,0.4,0.6],"15.20.00"])
    """
    assert fieldnames is not None
    assert action in ['delete', 'get', 'set']
    # for working with jsons see:
    # https://www.safaribooksonline.com/library/view/python-cookbook-3rd/9781449357337/ch06s02.html

    json_path = Path(row[json_col])
    with json_path.open() as j:
        data = json.load(j)

    if action == 'get':
        row = _get_fields(row, data, fieldnames)
    if action == 'set':
        data = _set_fields(data, fieldnames, values_to_set)
        write_json(json_path, data)
    if action == 'delete':
        _del_fields(data, fieldnames)
        write_json(json_path, data)

    return row


def host_is_hpc(sim=False, host_simulated="helix.nih.gov"):
    if sim:
        host = host_simulated
    else:
        host = platform.node()
    if any(h in host for h in ['biowulf', 'helix', 'felix']):
        hpc = True
    else:
        hpc = False

    return hpc


def _get_dev_str(options):
    if options.pop('dev'):
        dev_dir = options.pop('dev_dir')
        heud_path = \
            '/opt/conda/envs/neuro/lib/python2.7/site-packages/heudiconv'
        dev_str = ' --bind %s/heudiconv:%s' % (dev_dir, heud_path)
    else:
        dev_str = ""
        if options.pop('dev_dir'):
            raise ValueError("dev_dir can only be specified if dev = True")
    return dev_str, options


def _get_tmp_str(options):
    if options.pop('use_scratch'):
        tmp_str = ' --bind /lscratch/$SLURM_JOB_ID:/tmp'
    else:
        tmp_str = ' --bind /tmp:/tmp'
        if host_is_hpc():
            print('Not using scratch.')

    return tmp_str, options


def _get_setup():
    if host_is_hpc():
        setup = 'module load singularity;'
    else:
        setup = ""
    return setup

def _get_hbind():
    sing_home_tmp = Path('~/temp_for_singularity').expanduser()
    if not sing_home_tmp.exists():
        sing_home_tmp.mkdir()
    return f" -H {sing_home_tmp}"


def _get_heur(options):
    script = options.pop("heuristics_script")
    if not script:
        # use heuristics script inside container
        heur = ' -f /src/heudiconv/heudiconv/heuristics/convertall.py'
    else:
        path = Path('/data').joinpath(script).as_posix()
        heur = " -f %s" % script
    return heur, options


def _get_conv(options):
    if options.pop('conversion'):
        conv = ' -c dcm2niix'
    else:
        conv = ' -c none'

    return conv, options


def _get_outcmd(output_dir):
    if output_dir is not None:
        out = Path(output_dir).as_posix()
        out = f' -o {output_dir}'
    else:
        out = ""
    return out


def _get_other_cmds(options, options_dict):
    cmd = ''
    for k, v in options.items():
        if v:
            cmd += ' ' + options_dict[k]

    return cmd


def make_heud_call(*, row=None, project_dir=None, output_dir=None,
                   container_image=None, **kwargs):
    """
    Creates a command for executing heudiconv in a container.

    Parameters
    ----------
    row: pd.Series
        Dataframe row containing a column that has a path to a json.
    project_dir: pathlib.Path,string
        Should be the base directory (absolute path) of all projects work.
    output_dir: pathlib.Path,string
       Path to output directory relative to the project_dir.
    container_image: pathlib.Path,string
        Path to heudiconv singularity image.
    heuristics_script: default convertall.py within the container
        Path to heuristic script relative to project_dir
    anon_script: path, default None
    conversion: bool, default False
        Use dcm2niix to convert the dicoms.
    minmeta: bool, default False
        Remove the majority of the metadata.
    overwrite: bool, default True
        Overwrite previous output
    debug: bool, default False
        Drop into pdb upon error.
    dev: bool, default False
        Mount heudiconv code repo to container.
    dev_dir: pathlib.Path, string
        repo to be mounted to the container.
    use_scratch: bool, default False
        Mount /lscratch/$SLURM_JOB_ID to containers tmp directory.

    Returns
    -------
    cmd: string containing appropriate command

    Examples
    -------
    df.assign(cmd = lambda df:
        make_heud_call(row = df,
                     project_dir = project_dir_absolute,
                     output_dir=outdir,
                     conversion = False,
                     container_image = sing_image))
          )
    """
    if not isinstance(row, pd.Series):
        raise ValueError("row needs to be a pandas series object")
    options = OrderedDict({
        "heuristics_script": None,
        "anon_script": None,
        "conversion": False,
        "minmeta": False,
        "overwrite": True,
        "debug": False,
        "dev": False,
        "dev_dir": None,
        "use_scratch": False
    })
    options.update(kwargs)
    pbind = " --bind %s:/data" % Path(project_dir).as_posix()
    hbind = _get_hbind()
    img = ' %s' % Path(container_image).absolute()
    setup = _get_setup()
    dev_str, options = _get_dev_str(options)
    tmp_str, options = _get_tmp_str(options)
    heur, options = _get_heur(options)
    conv, options = _get_conv(options)
    outcmd = _get_outcmd(output_dir)

    # for options that simply append another flag
    options_dict = {
        "overwrite": '--overwrite',
        "debug": '--dbg',
        "minmeta": '--minmeta'
    }
    other_flags = _get_other_cmds(options, options_dict)

    cmd = \
        f"""\
{setup}singularity exec{pbind}{hbind}{dev_str}{tmp_str}{img}\
 bash -c '/neurodocker/startup.sh\
 heudiconv -d {row.dicom_template} -s {row.bids_subj} -ss {row.bids_ses}\
{heur}{conv}{outcmd} -p -b{other_flags}'\
"""

    output_dir = Path(output_dir).as_posix()
    return cmd


def get_symlink_name(row, symlinked_dicoms, sub_col='bids_subj',
                     ses_col='bids_ses', path_col='dicom_path'):
    symlink = \
        row[sub_col] + \
        '-' + row[ses_col] + \
        ''.join(Path(row[path_col]).suffixes)
    return symlink


def test_get_symlink_name():
    get_symlink_name


def make_symlink(row, overwrite_previous=False):
    """
    Dicoms are symlinked for running heudiconv v-0.2
    which has a slightly different interface and
    dictates that the files be named in a particular
    way
    """
    original_dir = Path.cwd()
    stdout = os.chdir(row.symlink_path.parent)
    if row.symlink_path.exists() and not overwrite_previous:
        symlinked = False
        print('Symlink exists already, supply "overwrite_previous" argument\
         if you wish to overwrite it')
    else:
        if row.symlink_path.exists():
            os.remove(row.symlink_path)
        stdout = row.symlink_path.symlink_to(
            Path('..').joinpath(row.dicom_path))
        symlinked = True
    stdout = os.chdir(original_dir)
    return symlinked


def make_symlink_template(row, project_dir_absolute):
    """
    Symlink template is required for heudiconv v-0.2
    which has a slightly different interface where
    the template must contain subject and session in
    braces
    """

    sym_dir_container = \
        Path('/data').joinpath(
            row.symlink_path.parent.relative_to(project_dir_absolute)
        )

    template = \
        sym_dir_container.as_posix() + \
        '/{subject}-{session}' + \
        '*' + \
        ''.join(Path(row.dicom_path).suffixes)
    return template


def __get_seqinfo_dict():
    key_list = ['total_files_till_now', 'example_dcm_file', 'series_id',
                'dcm_dir_name', 'unspecified2', 'unspecified3', 'dim1', 'dim2',
                'dim3', 'dim4', 'TR', 'TE', 'protocol_name',
                'is_motion_corrected', 'is_derived', 'patient_id',
                'study_description', 'referring_physician_name',
                'series_description', 'sequence_name', 'image_type',
                'accession_number', 'patient_age', 'patient_sex']

    seqinfo_dict = {k: np.nan for k in key_list}
    seqinfo_dict['series_id'] = 'id_for_dti'
    seqinfo_dict['series_description'] = 'a DTI series description'
    seqinfo_dict['dim1'] = 10
    return seqinfo_dict


def __get_seqinfo():
    seqinfo_dict = __get_seqinfo_dict()
    seqinfo_element = namedtuple('seqinfo_class', seqinfo_dict.keys())
    seqinfo = [seqinfo_element(**seqinfo_dict),
               seqinfo_element(**seqinfo_dict)]
    return seqinfo


def validate_heuristics_output(heuristics_script=None):
    """
    Run the bids validator on a dummy directory created from a
    heudiconv heuristics file.

    Parameters
    ----------
    heuristics_script: string,pathlib.Path, default is a sample from heudiconv_helpers.
        A path to a heuristics script to test.

    Returns
    -------
    validation_output: string
        bids validation output as a string
    """
    test_dir = __make_bids_tree(heuristics_script)

    validation = subprocess.run(
        'docker run --rm -v $PWD/bids_test:/data:ro\
         bids/validator:0.25.9 /data',
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE)
    if test_dir.exists():
        shutil.rmtree(test_dir, ignore_errors=False, onerror=None)

        error = validation.stderr.decode('utf-8')
        print("Stderr: ", error, '\n')
        return validation.stdout.decode('utf-8')


def __make_bids_tree(heuristics_script=None, test_dir=Path('bids_test/'),
                     clear_tree=False):
    """
    Create a dummy bids tree from a heuristics script for validation.

    Parameters
    ----------
    heuristics_script: string,pathlib.Path, default is a sample from heudiconv_helpers.
        A path to a heuristics script to test.
    test_dir: pathlib.Path, default is bids_test in current directory
        Path to output the bids tree to.
    clear_tree: bool
        If True, delete the directory at the test_dir path before
        creating a new one.

    Returns
    -------
    test_dir: pathlib.Path
        Path that the bids tree was output to.

    """
    if test_dir.exists():
        if clear_tree:
            shutil.rmtree(test_dir, ignore_errors=False, onerror=None)
        else:
            ValueError("The test_dir must either be a nonexistent directory or"
                       "clear_tree must be True.")
    if not shutil.which('docker'):
        raise EnvironmentError("Cannot find docker on path")
    if heuristics_script is None:
        import heudiconv_helpers.sample_heuristics as heur
    else:
        heur = hh_load_heuristic(Path(heuristics_script).as_posix())

    seqinfo = __get_seqinfo()
    thenifti = Path(hh.__file__).parent.parent.joinpath('data', 'test.nii.gz')
    templates_extracted = heur.infotodict(seqinfo)

    for subject in ['0001']:
        session = 'ses-0001'
        item = 1
        for template, _, _ in templates_extracted.keys():
            if template.find('derivatives') > -1:
                pass
            else:
                file = test_dir.joinpath(template.format(**locals()))
                os.makedirs('/'.join(file.parts[:-1]), exist_ok=True)
                file.with_suffix('.nii.gz').touch()
                # Create a json for each image
                file.with_suffix('.json').touch()
                modality = file.parts[-1].split('.')[0].split('_')[-1]

                # if the modality is dwi, create bval and bvec sidecars
                if modality == "dwi":
                    bvec_str = "0\n0\n0\n"
                    bval_str = "0\n"
                    file.with_suffix('.bval').write_text(bval_str)
                    file.with_suffix('.bvec').write_text(bvec_str)
                # if the modality is bold, create an events.tsv
                elif modality == "bold":
                    ev_fn = ('_'.join(file.parts[-1]
                                          .split('_')[:-1])
                             + '_events')
                    events_str = "onset\tduration\n"
                    # write events files
                    (file.parent / ev_fn).with_suffix('.tsv').write_text(events_str)

                # add a line to the scans.tsv
                ses_dir = Path(*file.parts[:-2])
                scans_file = (ses_dir / ('_'.join(ses_dir.parts[-2:])
                                         + '_scans.tsv'))
                try:
                    scans_str = scans_file.read_text()
                except FileNotFoundError:
                    scans_str = 'filename\tacq_time\n'
                scans_str += ((Path(*file.parts[-2:])
                               .with_suffix('.nii.gz').as_posix())
                              + '\t'
                              + (datetime.datetime.now()
                                 .strftime("%Y-%m-%dT%H:%M:%S"))
                              + '\n')
                # Write the scans file with the new line added
                scans_file.write_text(scans_str)

    return test_dir


def dry_run_heurs(heuristics_script=None, seqinfo=None, test_heuristics=False):
    """
    Check the output of a heuristics script.

    Parameters
    ----------
    heuristics_script: string,pathlib.Path, default is a sample from heudiconv_helpers.
        A path to a heuristics script to test.
    seqinfo: seqinfo object
        Object to run the heuristics on. If none a minimal default is used.
    test_heuristics: bool
        If true the heuristics script will execute all heuristics and actions
        to confirm that they evaluate properly.

    Returns
    -------
    df_scans: dataframe containing the scans captured by the heuristics. If
     test_heuiristics=True will return None.
    """
    if heuristics_script is None:
        import heudiconv_helpers.sample_heuristics as heur
    else:
        heuristics_script = Path(heuristics_script).absolute().as_posix()
        heur = hh_load_heuristic(heuristics_script)
    if not seqinfo:
        seqinfo = __get_seqinfo()
    heur_output = heur.infotodict(seqinfo, test_heuristics=test_heuristics)
    if not test_heuristics:
        dfs = []
        for k, v in heur_output.items():
            for v_i in v:
                dfs.append(pd.DataFrame([v_i[0], k[0]],
                                        index=["series_id", "template"]).T)
        series_map = pd.concat([df for df in dfs], axis=0)

        df_scans = series_map.merge(
            pd.DataFrame(seqinfo),
            on='series_id',
            how='outer')
        first_cols = ['series_id','template','series_description','sequence_name']
        df_scans = df_scans[first_cols + [c for c in df_scans if c not in first_cols] ]
    else:
        df_scans = None

    return df_scans


def hh_load_heuristic(heu_path):
    """Load heuristic from the file, return the module
    """
    heu_full_path = Path(heu_path).absolute().as_posix()
    path, fname = op.split(heu_full_path)
    try:
        old_syspath = sys.path[:]
        sys.path.append(path)
        mod = __import__(fname.split('.')[0])
        reload(mod)
        mod.filename = heu_full_path
    finally:
        sys.path = old_syspath

    return mod


def __mvrm_file(image_path, file, dest=None):
    """
    Move or remove a file from the bids tree containing an image_path.

    Parameters
    ----------
    image_path: pathlib.Path
        Path to the image being removed
    file: pathlib.Path
        Path to the file being removed
    dest: pathlib.Path
        root of the bids tree where you would like the deleted file moved.
        If None, the file will be removed.
    """
    if dest is not None:
        sub_part_bools = ['sub-' in ip for ip in image_path.parts]
        root_ind = np.array(range(len(image_path.parts)))[sub_part_bools][-2]
        file_dest = dest / Path(*file.parts[root_ind:])
        assert file_dest.name == file.name
        if not file_dest.parent.exists():
            file_dest.parent.mkdir(parents=True)
        shutil.move(file, file_dest)
    else:
        os.remove(file)


def __mvrm_bids_image(image_path, delete=False, dest=None):
    """
    Remove an image from a bids tree.
    Either by deleting the image and associated files or
    by moving it to a 'deleted_scans' directory in the
    parent of the bids tree or another specified destination.

    Parameters
    ----------
    image_path: pathlib.Path
        Path to the image being removed
    delete: bool
        Set to True to delete the files, otherwise they'll be moved.
    dest: pathlib.Path
        root of the bids tree where you would like the deleted file moved.
        Defaults to 'deleted_scans' in the parent of the bids tree.
    """
    # Get the base of the image_path and modality
    image_base = image_path.parent / image_path.parts[-1].split('.')[0]
    modality = image_path.parts[-1].split('.')[0].split('_')[-1]

    # Make a default destination for deleted files
    if not delete and dest is None:
        sub_part_bools = ['sub-' in ip for ip in image_path.parts]
        root_ind = np.array(range(len(image_path.parts)))[sub_part_bools][-2]
        dest = Path(
            *(image_path.parts[:root_ind - 1] + tuple(['deleted_scans'])))

    # Edit the scans.tsv
    ses_dir = Path(*image_path.parts[:-2])
    scans_file = (ses_dir / ('_'.join(ses_dir.parts[-2:]) + '_scans.tsv'))
    orig_scans = scans_file.read_text().split('\n')
    new_scans = [ss for ss in orig_scans
                 if Path(*image_path.parts[-2:]).as_posix() not in ss]
    # Sanity check to make sure only one entry was removed before rewriting
    assert len(orig_scans) == (len(new_scans) + 1)
    scans_file.write_text('\n'.join(new_scans))

    # Remove or move all the files that share a name with the nifti
    # to be deleted
    for file in image_base.parent.glob(image_base.name + '*'):
        __mvrm_file(image_path, file, dest=dest)
    # Deal with the events file for bolds
    if modality == "bold":
        ev_fn = ('_'.join(image_path.parts[-1]
                                    .split('_')[:-1])
                 + '_events.tsv')
        event_file = image_path.parent / ev_fn
        __mvrm_file(image_path, event_file, dest=dest)

    # remove parent if the directory is empty now
    if len(list(image_base.parent.iterdir())) == 0:
        image_base.parent.rmdir()


def mvrm_bids_image(row, delete=False, dest=None):
    """
    Remove an images specified in the image_path field of a row
    from a bids tree. Either by deleting the image and associated files or
    by moving it to a 'deleted_scans' directory in the
    parent of the bids tree or another specified destination.

    Parameters
    ----------
    row: pandas.Series
        Row containing an image_path field for the image to be removed.
    delete: bool
        Set to True to delete the files, otherwise they'll be moved.
    dest: pathlib.Path
        root of the bids tree where you would like the deleted file moved.
        Defaults to 'deleted_scans' in the parent of the bids tree.
    """
    __mvrm_bids_image(row.image_path, delete=delete, dest=dest)


def flatten(items):
    """Yield items from any nested iterable; from beazley's python cookbook."""
    for x in items:
        if isinstance(x, Iterable) and not isinstance(x, (str, bytes)):
            yield from flatten(x)
        else:
            yield x

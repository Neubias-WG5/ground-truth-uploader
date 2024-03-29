import os
from argparse import ArgumentParser, Namespace
from pathlib import Path

import imageio
from biaflows.helpers.data_preparation import download_images, prepare_data, download_attached
from cytomine import Cytomine

from biaflows.helpers import upload_data
from cytomine.cytomine import _cytomine_parameter_name_synonyms
from cytomine.models import Project, AnnotationCollection
from cytomine.models.track import TrackCollection
from imageio import volread

from swc_to_tiff_stack import swc_to_tiff_stack


class FakeJob(object):
    """To be used in place of a BiaflowsJob in download_iamges and upload_data"""
    def __init__(self, project):
        self._project = project
        self._params = Namespace()
        self._params.cytomine_id_project = project.id

    @property
    def job(self):
        class FJ(object):
            def update(*args, **kwargs):
                return

            @property
            def id(self):
                return "gt"
        return FJ()

    @property
    def flags(self):
        return {"do_download": True, "do_upload_annotations": True, "tiling": False}

    @property
    def parameters(self):
        return self._params

    @property
    def project(self):
        return self._project

    def monitor(self, data, **kwargs):
        for d in data:
            yield d


def guess_dims(in_path):
    """Return true if the first input image read is 2-dimensional"""
    files = os.listdir(in_path)
    if len(files) == 0:
        raise ValueError("Input files not found.")
    filepath = os.path.join(in_path, files[0])
    vol = volread(filepath)
    if len(vol.shape) == 5 and vol.shape[0] == 1 and vol.shape[1] == 1 and vol.shape[2] == 1:
        return True
    else:
        return vol.ndim == 2


def delete_collection(collec, name="annotation"):
    if len(collec) > 0:
        print("Deleting {} existing {}(s).".format(len(collec), name))
        failure = 0
        for annotation in collec:
            if not annotation.delete():
                failure += 1

        if failure > 0:
            print("{} {}(s) could not be deleted.".format(failure, name))


def main(argv):
    parser = ArgumentParser()
    parser.add_argument(*_cytomine_parameter_name_synonyms("project_id"),
                        dest="project_id", type=int, help="The Cytomine project id.", required=True)
    parser.add_argument("-i", "--ignore-existing", action="store_true", dest="ignore_existing",
                        help="Ignore existing ground truth annotation associated with the project. If not specified,"
                             " current annotations will be deleted before uploading the new ones.")
    parser.set_defaults(ignore_existing=False)
    options, _ = parser.parse_known_args(argv)

    with Cytomine.connect_from_cli(argv) as cytomine:
        project = Project().fetch(options.project_id)
        print("Project '{}' (#{}): discipline '{}'".format(project.name, project.id, project.disciplineShortName))

        if not options.ignore_existing:
            annotations = AnnotationCollection()
            annotations.project = project.id
            annotations.user = cytomine.current_user.id
            annotations.fetch()
            delete_collection(annotations, "annotation")

            tracks = TrackCollection()
            tracks.project = project.id
            tracks.user = cytomine.current_user.id
            tracks.fetch_with_filter("project", project.id)
            tracks._data = [t for t in tracks.data() if t.name.startswith("gt-")]
            delete_collection(tracks, "track")

        fake_job = FakeJob(project)
        home = Path.home()
        in_path = os.path.join(home, "data", "in")
        gt_path = os.path.join(home, "data", "gt")
        os.makedirs(in_path)
        os.makedirs(gt_path)
        in_images, gt_images = download_images(fake_job, in_path, gt_path, gt_suffix="_lbl")

        if project.disciplineShortName == "TreTrc":
            # ground truth is contained in swc files so need to
            # convert them into masks beforehand
            print("TreTrc problem: start converting SWC to masks")
            download_attached(in_images, gt_path, do_download=True)
            alternate_gt_path = os.path.join(home, "data", "altgt")
            os.makedirs(alternate_gt_path)
            for in_image in in_images:
                swc_filepath = in_image.attached[0].filepath
                im_size = imageio.volread(in_image.filepath).shape  # Size is Depth,Height,Width
                im_size = im_size[::-1]  # Invert the size order to Width,Height,Depth
                swc_to_tiff_stack(
                    input_path=swc_filepath,
                    output_path=os.path.join(alternate_gt_path, in_image.filename),
                    im_size=im_size
                )
            gt_path = alternate_gt_path

        is_2d = guess_dims(gt_path)
        print("Image detected as {}".format("2d" if is_2d else ">2d"))
        upload_data(problemclass=project.disciplineShortName,
                    nj=fake_job, inputs=in_images, out_path=gt_path,
                    is_2d=is_2d, projection=-1)


if __name__ == "__main__":
    import sys
    main(sys.argv[1:])

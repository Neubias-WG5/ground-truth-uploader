import os
from argparse import ArgumentParser, Namespace
from pathlib import Path

from biaflows.helpers.data_preparation import download_images
from cytomine import Cytomine

from biaflows.helpers import prepare_data, upload_data
from cytomine.cytomine import _cytomine_parameter_name_synonyms
from cytomine.models import Project
from imageio import volread


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
    return vol.ndim == 2


def main(argv):
    parser = ArgumentParser()
    parser.add_argument(*_cytomine_parameter_name_synonyms("project_id"),
                        dest="project_id", type=int, help="The Cytomine project id.", required=True)
    options, _ = parser.parse_known_args(argv)

    with Cytomine.connect_from_cli(argv):
        project = Project().fetch(options.project_id)
        print("Project #{}: discipline '{}'".format(project.id, project.disciplineShortName))
        fake_job = FakeJob(project)
        home = Path.home()
        in_path = os.path.join(home, "data", "in")
        gt_path = os.path.join(home, "data", "gt")
        os.makedirs(in_path)
        os.makedirs(gt_path)
        in_images, gt_images = download_images(fake_job, in_path, gt_path, gt_suffix="_lbl")
        is_2d = guess_dims(in_path)
        print("Image detected as {}".format("2d" if is_2d else ">2d"))
        upload_data(problemclass=project.disciplineShortName,
                    nj=fake_job, inputs=in_images, out_path=gt_path,
                    is_2d=is_2d)




if __name__ == "__main__":
    import sys

    main(sys.argv[1:])

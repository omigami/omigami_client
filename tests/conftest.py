import json
import os
import pickle
from pathlib import Path
from typing import Dict
from unittest.mock import Mock

import pytest
from requests import Response

from omigami.authentication import encrypt_credentials, AUTH
from omigami.omi_settings import config
from omigami.spectra_matching import Spec2Vec, MS2DeepScore

ASSETS_DIR = Path(__file__).parent / "assets"


def _set_credentials_and_auth_for_tests():
    """
    This uses the default dev credentials "omigami@dev.org" and setup necessary variable values for testing
    """
    username = (
        os.getenv("TEST_OMIGAMI_USERNAME") or config["login"]["dev"]["username"].get()
    )
    pwd = os.getenv("TEST_OMIGAMI_PWD") or config["login"]["dev"]["password"].get()
    AUTH.credentials = encrypt_credentials(username, pwd)


@pytest.fixture(scope="module")
def spec2vec_client():
    _set_credentials_and_auth_for_tests()
    client = Spec2Vec()
    return client


@pytest.fixture(scope="module")
def ms2deepscore_client():
    _set_credentials_and_auth_for_tests()
    client = MS2DeepScore()
    return client


@pytest.fixture(scope="session")
def mgf_46_spectra_path():
    """Mgf file containing 46 spectra"""
    return str(ASSETS_DIR / "gnps_small.mgf")


@pytest.fixture(scope="session")
def mgf_377_spectra_path():
    return str(ASSETS_DIR / "GNPS-COLLECTIONS-MISC.mgf")


@pytest.fixture(scope="session")
def mgf_huge_path():
    return str(ASSETS_DIR / "GNPS-NIST14-MATCHES.mgf")


@pytest.fixture(scope="session")
def sample_response():
    with open(ASSETS_DIR / "sample_response.pickle", "rb") as f:
        response = pickle.load(f)

    return response


@pytest.fixture()
def ms2deepscore_prediction_endpoints():
    _client = Spec2Vec()
    return {
        "positive": _client._PREDICT_ENDPOINT_BASE.format(
            algorithm="ms2deepscore", ion_mode="positive"
        ),
        "negative": _client._PREDICT_ENDPOINT_BASE.format(
            algorithm="ms2deepscore", ion_mode="negative"
        ),
    }


@pytest.fixture(scope="session")
def mgf_path_of_2_spectra():
    return str(ASSETS_DIR / "gnps_2_spectra.mgf")


@pytest.fixture()
def spec2vec_prediction_endpoints():
    _client = Spec2Vec()
    return {
        "positive": _client._PREDICT_ENDPOINT_BASE.format(
            algorithm="spec2vec", ion_mode="positive"
        ),
        "negative": _client._PREDICT_ENDPOINT_BASE.format(
            algorithm="spec2vec", ion_mode="negative"
        ),
    }


@pytest.fixture(scope="session")
def spectra_match_data_path():
    return str(ASSETS_DIR / "spectrum_matches.csv")


@pytest.fixture(scope="session")
def spectra_match_data_path_missing_smiles():
    return str(ASSETS_DIR / "spectrum_missing_smiles.csv")


@pytest.fixture(scope="session")
def spectra_match_data_path_web_api_error():
    return str(ASSETS_DIR / "spectrum_matches_error_on_classyfire.csv")


@pytest.fixture
def response_100_spectra_json():
    with open(ASSETS_DIR / "response_100_spectra.json", "r") as f:
        response_json = json.load(f)

    return response_json


@pytest.fixture
def response_10_spectra(response_100_spectra_json):
    response = Response()
    response.json = lambda: _get_sized_response(10, response_100_spectra_json)
    return response


@pytest.fixture
def mock_send_request(response_100_spectra_json) -> Mock:
    def send_request(batch, *args):
        """Returns a response in the correct format with the size of the input spectra"""
        response = Response()
        response.json = lambda: _get_sized_response(
            len(batch), response_100_spectra_json
        )

        return response

    return Mock(side_effect=send_request)


def _get_sized_response(size: int, json_data: Dict[str, dict]) -> Dict[str, dict]:
    """
    We have a response fixture of 100 spectra in a json asset. For some tests we want
    to query with smaller payloads (e.g. 25 spectra) and the correct response should
    also be of this size. This function changes the size of the 100 spectra response
    to an integer number between 1 and 100.
    """
    spectrum_ids = list(json_data["jsonData"].keys())[:size]
    response_data = {
        "jsonData": {id_: json_data["jsonData"][id_] for id_ in spectrum_ids}
    }
    return response_data

import ast
import json
from logging import getLogger
from typing import Dict, Union, List, Optional

import pandas as pd
import requests
from matchms import Spectrum
from matchms.importing import load_from_mgf

SPECTRA_LIMIT_PER_REQUEST = 100
Payload = Dict[str, Dict[str, Dict[str, Union[int, dict]]]]
log = getLogger(__file__)

JSON = Union[List[dict], dict]


class InvalidCredentials(Exception):
    pass


class Spec2Vec:
    _endpoint_url = (
        "https://omigami.datarevenue.com/seldon/seldon/spec2vec/api/v0.1/predictions"
    )

    def __init__(self, token: str):
        self._token = token

    def match_spectra_from_path(
        self, mgf_path: str, n_best: int, include_metadata: List[str] = None
    ) -> List[pd.DataFrame]:
        """
        Finds the N best matches for spectra in a local mgf file using spec2vec algorithm.

        Parameters
        ----------
        mgf_path: str
            Local path to mgf file
        n_best:
            Number of best matches to select
        include_metadata: List[str]
            Metadata keys to include in the response. Will make response slower. Please
            check the documentation for a list of valid keys.

        Returns
        -------
        A list of pandas dataframes containing the best matches and optionally metadata
        for these matches.

        """

        spectra_generator = load_from_mgf(mgf_path)

        # issue requests respecting the spectra limit per request
        batch = []
        requests = []
        for spectrum in spectra_generator:
            batch.append(spectrum)
            if len(batch) == SPECTRA_LIMIT_PER_REQUEST:
                payload = self._build_payload(batch, n_best, include_metadata)
                requests.append(self._send_request(payload))
                batch = []
        if batch:
            payload = self._build_payload(batch, n_best)
            requests.append(self._send_request(payload))

        predictions = []
        for r in requests:
            predictions.extend(self._format_results(r))
        return predictions

    def _build_payload(
        self,
        batch: List[Spectrum],
        n_best_spectra: int,
        include_metadata: Optional[List[str]],
    ) -> JSON:
        """Extract abundance pairs and Precursor_MZ data, then build the json payload

        Returns:
        --------
        - payload: JSON
            the full request payload with input data
        """
        spectra = []
        for spectrum in batch:
            spectra.append(
                {
                    "peaks_json": str(
                        [
                            [mz, intensity]
                            for mz, intensity in zip(
                                spectrum.peaks.mz, spectrum.peaks.intensities
                            )
                        ]
                    ),
                    "Precursor_MZ": str(spectrum.metadata["pepmass"][0]),
                }
            )

        log.info(f"{len(spectra)} spectra found on input file.")
        self._validate_input(spectra)

        payload = {
            "data": {
                "ndarray": {
                    "parameters": {
                        "n_best_spectra": n_best_spectra,
                        "include_metadata": include_metadata,
                    },
                    "data": spectra,
                }
            }
        }
        return payload

    @staticmethod
    def _validate_input(model_input: List[Dict]):
        for i, spectrum in enumerate(model_input):
            if not isinstance(spectrum, Dict):
                raise TypeError(
                    f"Spectrum data must be a dictionary. Passed type: {type(spectrum)}"
                )

            mandatory_keys = ["peaks_json", "Precursor_MZ"]
            if any(key not in spectrum.keys() for key in mandatory_keys):
                raise KeyError(
                    f"Please include all the mandatory keys in your input data. "
                    f"The mandatory keys are {mandatory_keys}",
                )

            if isinstance(spectrum["peaks_json"], str):
                try:
                    ast.literal_eval(spectrum["peaks_json"])
                except SyntaxError:
                    raise ValueError(
                        "peaks_json needs to be a valid python string representation of "
                        "a list or a list. Passed value: {spectrum['peaks_json']}",
                        400,
                    )
            elif not isinstance(spectrum["peaks_json"], list):
                raise ValueError(
                    "peaks_json needs to be a valid python string representation of a "
                    f"list or a list. Passed value: {spectrum['peaks_json']}",
                    400,
                )

            float_keys = ["Precursor_MZ", "Charge"]
            for key in float_keys:
                if spectrum.get(key):
                    try:
                        float(spectrum[key])
                    except ValueError:
                        raise ValueError(
                            f"{key} needs to be a string representation of a float. "
                            f"Passed value: {spectrum[key]}",
                            400,
                        )

    def _send_request(self, payload: Payload) -> requests.Response:
        api_request = requests.post(
            self._endpoint_url,
            json=payload,
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=600,
        )

        if api_request.status_code == 401:
            raise InvalidCredentials(
                "Your credentials are invalid, please revise your API token."
            )
        return api_request

    @staticmethod
    def _format_results(api_request: requests.Response) -> List[pd.DataFrame]:
        response = json.loads(api_request.text)
        library_spectra_raw = response["data"]["ndarray"]

        predicted_spectra = []
        for i in range(len(library_spectra_raw)):
            library_spectra_dataframe = pd.DataFrame(
                data=[spectrum["score"] for spectrum in library_spectra_raw[i]],
                index=[
                    spectrum["match_spectrum_id"] for spectrum in library_spectra_raw[i]
                ],
                columns=["score"],
            )
            library_spectra_dataframe.index.name = f"matches of spectrum #{i + 1}"
            predicted_spectra.append(library_spectra_dataframe)

        return predicted_spectra

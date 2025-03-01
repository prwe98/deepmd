# SPDX-License-Identifier: LGPL-3.0-or-later
from typing import (
    Optional,
)

import torch

from deepmd.pt.model.atomic_model import (
    LinearEnergyAtomicModel,
)
from deepmd.pt.model.model.model import (
    BaseModel,
)
from deepmd.utils.data_system import (
    DeepmdDataSystem,
)

from .dp_model import (
    DPModelCommon,
)
from .make_model import (
    make_model,
)

DPLinearModel_ = make_model(LinearEnergyAtomicModel)


@BaseModel.register("linear_ener")
class LinearEnergyModel(DPLinearModel_):
    model_type = "linear_ener"

    def __init__(
        self,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

    def translated_output_def(self):
        out_def_data = self.model_output_def().get_data()
        output_def = {
            "atom_energy": out_def_data["energy"],
            "energy": out_def_data["energy_redu"],
        }
        if self.do_grad_r("energy"):
            output_def["force"] = out_def_data["energy_derv_r"]
            output_def["force"].squeeze(-2)
        if self.do_grad_c("energy"):
            output_def["virial"] = out_def_data["energy_derv_c_redu"]
            output_def["virial"].squeeze(-2)
            output_def["atom_virial"] = out_def_data["energy_derv_c"]
            output_def["atom_virial"].squeeze(-3)
        if "mask" in out_def_data:
            output_def["mask"] = out_def_data["mask"]
        return output_def

    def forward(
        self,
        coord,
        atype,
        box: Optional[torch.Tensor] = None,
        fparam: Optional[torch.Tensor] = None,
        aparam: Optional[torch.Tensor] = None,
        do_atomic_virial: bool = False,
    ) -> dict[str, torch.Tensor]:
        model_ret = self.forward_common(
            coord,
            atype,
            box,
            fparam=fparam,
            aparam=aparam,
            do_atomic_virial=do_atomic_virial,
        )

        model_predict = {}
        model_predict["atom_energy"] = model_ret["energy"]
        model_predict["energy"] = model_ret["energy_redu"]
        if self.do_grad_r("energy"):
            model_predict["force"] = model_ret["energy_derv_r"].squeeze(-2)
        if self.do_grad_c("energy"):
            model_predict["virial"] = model_ret["energy_derv_c_redu"].squeeze(-2)
            if do_atomic_virial:
                model_predict["atom_virial"] = model_ret["energy_derv_c"].squeeze(-3)
        else:
            model_predict["force"] = model_ret["dforce"]
        if "mask" in model_ret:
            model_predict["mask"] = model_ret["mask"]
        return model_predict

    @torch.jit.export
    def forward_lower(
        self,
        extended_coord,
        extended_atype,
        nlist,
        mapping: Optional[torch.Tensor] = None,
        fparam: Optional[torch.Tensor] = None,
        aparam: Optional[torch.Tensor] = None,
        do_atomic_virial: bool = False,
    ):
        model_ret = self.forward_common_lower(
            extended_coord,
            extended_atype,
            nlist,
            mapping=mapping,
            fparam=fparam,
            aparam=aparam,
            do_atomic_virial=do_atomic_virial,
            extra_nlist_sort=self.need_sorted_nlist_for_lower(),
        )

        model_predict = {}
        model_predict["atom_energy"] = model_ret["energy"]
        model_predict["energy"] = model_ret["energy_redu"]
        if self.do_grad_r("energy"):
            model_predict["extended_force"] = model_ret["energy_derv_r"].squeeze(-2)
        if self.do_grad_c("energy"):
            model_predict["virial"] = model_ret["energy_derv_c_redu"].squeeze(-2)
            if do_atomic_virial:
                model_predict["extended_virial"] = model_ret["energy_derv_c"].squeeze(
                    -3
                )
        else:
            assert model_ret["dforce"] is not None
            model_predict["dforce"] = model_ret["dforce"]
        return model_predict

    @classmethod
    def update_sel(
        cls,
        train_data: DeepmdDataSystem,
        type_map: Optional[list[str]],
        local_jdata: dict,
    ) -> tuple[dict, Optional[float]]:
        """Update the selection and perform neighbor statistics.

        Parameters
        ----------
        train_data : DeepmdDataSystem
            data used to do neighbor statistics
        type_map : list[str], optional
            The name of each type of atoms
        local_jdata : dict
            The local data refer to the current class

        Returns
        -------
        dict
            The updated local data
        float
            The minimum distance between two atoms
        """
        local_jdata_cpy = local_jdata.copy()
        type_map = local_jdata_cpy["type_map"]
        min_nbor_dist = None
        for idx, sub_model in enumerate(local_jdata_cpy["models"]):
            if "tab_file" not in sub_model:
                sub_model, temp_min = DPModelCommon.update_sel(
                    train_data, type_map, local_jdata["models"][idx]
                )
                if min_nbor_dist is None or temp_min <= min_nbor_dist:
                    min_nbor_dist = temp_min
        return local_jdata_cpy, min_nbor_dist

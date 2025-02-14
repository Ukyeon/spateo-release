try:
    from typing import Any, List, Literal, Tuple, Union
except ImportError:
    from typing_extensions import Literal

from typing import List, Optional, Tuple, Union

import numpy as np
from anndata import AnnData

from .methods import BA_align, empty_cache
from .transform import BA_transform, BA_transform_and_assignment
from .utils import _iteration, downsampling


def morpho_align(
    models: List[AnnData],
    layer: str = "X",
    genes: Optional[Union[list, np.ndarray]] = None,
    spatial_key: str = "spatial",
    key_added: str = "align_spatial",
    iter_key_added: Optional[str] = "iter_spatial",
    vecfld_key_added: str = "VecFld_morpho",
    mode: Literal["S", "N", "SN"] = "SN",
    dissimilarity: str = "kl",
    max_iter: int = 100,
    label_key: Optional[str] = None,
    dtype: str = "float64",
    device: str = "cpu",
    verbose: bool = True,
    **kwargs,
) -> Tuple[List[AnnData], List[np.ndarray], List[np.ndarray]]:
    """
    Continuous alignment of spatial transcriptomic coordinates based on Morpho.

    Args:
        models: List of models (AnnData Object).
        layer: If ``'X'``, uses ``.X`` to calculate dissimilarity between spots, otherwise uses the representation given by ``.layers[layer]``.
        genes: Genes used for calculation. If None, use all common genes for calculation.
        spatial_key: The key in ``.obsm`` that corresponds to the raw spatial coordinate.
        key_added: ``.obsm`` key under which to add the aligned spatial coordinate.
        iter_key_added: ``.uns`` key under which to add the result of each iteration of the iterative process. If ``iter_key_added``  is None, the results are not saved.
        vecfld_key_added: The key that will be used for the vector field key in ``.uns``. If ``vecfld_key_added`` is None, the results are not saved.
        mode: The method of alignment. Available ``mode`` are: ``'S'``, ``'N'`` and ``'SN'``.
        dissimilarity: Expression dissimilarity measure: ``'kl'`` or ``'euclidean'``.
        max_iter: Max number of iterations for morpho alignment.
        dtype: The floating-point number type. Only ``float32`` and ``float64``.
        device: Equipment used to run the program. You can also set the specified GPU for running. ``E.g.: '0'``.
        verbose: If ``True``, print progress updates.
        **kwargs: Additional parameters that will be passed to ``BA_align`` function.

    Returns:
        align_models: List of models (AnnData Object) after alignment.
        pis: List of pi matrices.
        sigma2s: List of sigma2.
    """
    for m in models:
        m.obsm[key_added] = m.obsm[spatial_key]
    for m in models:
        m.obsm["Rigid_3d_align_spatial"] = m.obsm[spatial_key]
    for m in models:
        m.obsm["Coarse_alignment"] = m.obsm[spatial_key]
    for m in models:
        m.obsm["optimal_RnA"] = m.obsm[spatial_key]

    pis, sigma2s = [], []
    align_models = [model.copy() for model in models]
    progress_name = f"Models alignment based on morpho, mode: {mode}."
    for i in _iteration(n=len(align_models) - 1, progress_name=progress_name, verbose=True):
        modelA = align_models[i]
        modelB = align_models[i + 1]
        if label_key is not None:
            # calculate label similarity
            catA = modelA.obs[label_key]
            catB = modelB.obs[label_key]
            UnionCategories = np.union1d(catA.cat.categories, catB.cat.categories)
            catACode, catBCode = np.zeros(catA.shape, dtype=int), np.zeros(catB.shape, dtype=int)
            for code, cat in enumerate(UnionCategories):
                if cat == "unknown":
                    code = -1
                catACode[catA == cat] = code
                catBCode[catB == cat] = code
            LabelSimMat = np.zeros((catA.shape[0], catB.shape[0]))
            for index in range(catB.shape[0]):
                LabelSimMat[:, index] = catACode != catBCode[i]
            LabelSimMat = LabelSimMat.T
        else:
            LabelSimMat = None
        _, P, sigma2 = BA_align(
            sampleA=modelA,
            sampleB=modelB,
            genes=genes,
            spatial_key="optimal_RnA",
            key_added=key_added,
            iter_key_added=iter_key_added,
            vecfld_key_added=vecfld_key_added,
            layer=layer,
            mode=mode,
            dissimilarity=dissimilarity,
            max_iter=max_iter,
            dtype=dtype,
            device=device,
            inplace=True,
            verbose=verbose,
            added_similarity=LabelSimMat,
            **kwargs,
        )
        (_, _, modelB.obsm["Rigid_align_spatial"],) = BA_transform(
            vecfld=modelB.uns[vecfld_key_added],
            quary_points=modelB.obsm[spatial_key],
            device=device,
            dtype=dtype,
        )
        pis.append(P)
        sigma2s.append(sigma2)
        empty_cache(device=device)

    return align_models, pis, sigma2s


def morpho_align_ref(
    models: List[AnnData],
    models_ref: Optional[List[AnnData]] = None,
    n_sampling: Optional[int] = 2000,
    sampling_method: str = "trn",
    layer: str = "X",
    genes: Optional[Union[list, np.ndarray]] = None,
    spatial_key: str = "spatial",
    key_added: str = "align_spatial",
    iter_key_added: Optional[str] = "iter_spatial",
    vecfld_key_added: Optional[str] = "VecFld_morpho",
    mode: Literal["S", "N", "SN"] = "SN",
    dissimilarity: str = "kl",
    max_iter: int = 100,
    return_full_assignment: bool = True,
    dtype: str = "float64",
    device: str = "cpu",
    verbose: bool = True,
    **kwargs,
) -> Tuple[List[AnnData], List[AnnData], List[np.ndarray], List[np.ndarray], List[np.ndarray]]:
    """
    Continuous alignment of spatial transcriptomic coordinates with the reference models based on Morpho.

    Args:
        models: List of models (AnnData Object).
        models_ref: Another list of models (AnnData Object).
        n_sampling: When ``models_ref`` is None, new data containing n_sampling coordinate points will be automatically generated for alignment.
        sampling_method: The method to sample data points, can be one of ``["trn", "kmeans", "random"]``.
        layer: If ``'X'``, uses ``.X`` to calculate dissimilarity between spots, otherwise uses the representation given by ``.layers[layer]``.
        genes: Genes used for calculation. If None, use all common genes for calculation.
        spatial_key: The key in ``.obsm`` that corresponds to the raw spatial coordinate.
        key_added: ``.obsm`` key under which to add the aligned spatial coordinate.
        iter_key_added: ``.uns`` key under which to add the result of each iteration of the iterative process. If ``iter_key_added``  is None, the results are not saved.
        vecfld_key_added: The key that will be used for the vector field key in ``.uns``. If ``vecfld_key_added`` is None, the results are not saved.
        mode: The method of alignment. Available ``mode`` are: ``'S'``, ``'N'`` and ``'SN'``.
        dissimilarity: Expression dissimilarity measure: ``'kl'`` or ``'euclidean'``.
        max_iter: Max number of iterations for morpho alignment.
        dtype: The floating-point number type. Only ``float32`` and ``float64``.
        device: Equipment used to run the program. You can also set the specified GPU for running. ``E.g.: '0'``.
        verbose: If ``True``, print progress updates.
        **kwargs: Additional parameters that will be passed to ``BA_align`` function.

    Returns:
        align_models: List of models (AnnData Object) after alignment.
        align_models_ref: List of models_ref (AnnData Object) after alignment.
        pis: List of pi matrices for models.
        pis_ref: List of pi matrices for models_ref.
        sigma2s: List of sigma2.
    """

    # Downsampling
    if models_ref is None:
        models_sampling = [model.copy() for model in models]
        models_ref = downsampling(
            models=models_sampling,
            n_sampling=n_sampling,
            sampling_method=sampling_method,
            spatial_key=spatial_key,
        )

    pis, pis_ref, sigma2s = [], [], []
    align_models = [model.copy() for model in models]
    align_models_ref = [model.copy() for model in models_ref]
    for model in align_models_ref:
        model.obsm[key_added] = model.obsm[spatial_key]
    align_models[0].obsm[key_added] = align_models[0].obsm[spatial_key]
    progress_name = f"Models alignment with ref-models based on morpho, mode: {mode}."
    for i in _iteration(n=len(align_models) - 1, progress_name=progress_name, verbose=True):
        modelA_ref = align_models_ref[i]
        modelB_ref = align_models_ref[i + 1]

        _, P, sigma2 = BA_align(
            sampleA=modelA_ref,
            sampleB=modelB_ref,
            genes=genes,
            spatial_key=key_added,
            key_added=key_added,
            iter_key_added=iter_key_added,
            vecfld_key_added=vecfld_key_added,
            layer=layer,
            mode=mode,
            dissimilarity=dissimilarity,
            max_iter=max_iter,
            dtype=dtype,
            device=device,
            inplace=True,
            verbose=verbose,
            **kwargs,
        )
        align_models_ref[i + 1] = modelB_ref
        pis_ref.append(P)
        sigma2s.append(sigma2)

        modelA, modelB = align_models[i], align_models[i + 1]
        modelB.uns[vecfld_key_added] = modelB_ref.uns[vecfld_key_added]
        if return_full_assignment:
            P, modelB.obsm[key_added] = BA_transform_and_assignment(
                samples=[modelB, modelA],
                vecfld=modelB_ref.uns[vecfld_key_added],
                genes=genes,
                layer=layer,
                small_variance=True,
                spatial_key=spatial_key,
                device=device,
                dtype=dtype,
                **kwargs,
            )
        else:
            modelB.obsm[key_added], _, modelB.obsm["Rigid_align_spatial"] = BA_transform(
                vecfld=modelB_ref.uns[vecfld_key_added],
                quary_points=modelB.obsm[spatial_key],
                device=device,
                dtype=dtype,
            )

        pis.append(P)

    return align_models, align_models_ref, pis, pis_ref, sigma2s

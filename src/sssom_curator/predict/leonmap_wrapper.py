# /// script
# requires-python = ">=3.11,<3.12"
# dependencies = [
#     "leonmap @ git+https://github.com/HarshitSoni1903/Weakly-Supervised-Representation-Learning-for-Cross-Ontology-Mapping.git",
#     "mapnet @ git+https://github.com/gyorilab/mapnet.git@969d11b915",
#     "openacme @ git+https://github.com/gyorilab/openacme.git",
#     "biomappings==0.4.2",
#     "sssom-pydantic>=0.5.1",
#     "pyobo==0.12.18",
#     "bioregistry==0.13.23",
#     "bioversions==0.8.289",
#     "bioontologies==0.7.4",
#     "networkx==3.6.1",
#     "polars==1.39.3",
#     "pandas==2.3.3",
#     "pyarrow",
#     "pystow>=0.8.6",
#     "faiss-cpu==1.13.2",
#     "huggingface-hub",
# ]
#
# [tool.uv]
# override-dependencies = [
#     "torchvision ; sys_platform == 'nope'",
#     "torchaudio ; sys_platform == 'nope'",
#     "deeponto ; sys_platform == 'nope'",
#     "jpype1 ; sys_platform == 'nope'",
#     "black ; sys_platform == 'nope'",
#     "indra ; sys_platform == 'nope'",
#     "pysb ; sys_platform == 'nope'",
#     "transformers>=4.44",
# ]
# ///
"""WHO ICD-10 -> full MeSH with leonmap (SapBERT + FAISS), a depth-decayed tree blend, and lexical-hit labeling.

uv run --script https://raw.githubusercontent.com/gyorilab/mapnet/refs/heads/main/scripts/generate_leonmap_mesh_icd10_mapping.py
"""

import argparse
import importlib.metadata as md
import json
import os
import re
import sys
from datetime import date
from itertools import chain
from pathlib import Path

import bioontologies.robot
import curies
import faiss
import networkx as nx
import numpy as np
import pandas as pd
import polars as pl
import pystow
import sssom_pydantic
from biomappings.resources import POSITIVES_SSSOM_PATH, PREDICTIONS_SSSOM_PATH
from huggingface_hub import snapshot_download
from openacme.icd10.icd10 import ICD10_XML_URL, get_icd10_graph
from openacme.icd10.map_definitions import map_icd10_to_definitions

if not hasattr(bioontologies.robot, "ROBOT_COMMAND"):
    bioontologies.robot.ROBOT_COMMAND = ["robot"]

faiss.get_num_gpus = lambda: 0

from leonmap import config
from leonmap.config import COLLECTIONS, MAPPINGS, BuildConfig, resolve_path
from leonmap.utils import canonicalize_id, load_collection
from mapnet.utils.filtering import (
    get_right_wrong_mappings,
    repair_names_with_semra,
)
from mapnet.utils.utils import make_undirected, sssom_to_biomappings

HF_MODEL_REPO = "harshitsoni1903/sapbert-finetuned-semra"
MESH_OWL_GZ_URL = "https://w3id.org/biopragmatics/resources/mesh/mesh.owl.gz"
SEMRA_URL = "https://zenodo.org/records/15826693/files/processed.sssom.tsv.gz?download=1"
SEMRA_NAME = "semra_disease_landscape_mappings.tsv.gz"
MAPPING_TOOL = (
    "https://github.com/gyorilab/mapnet/blob/main/scripts/generate_leonmap_mesh_icd10_mapping.py"
)

STUDY = "icd10_mesh_full"

PREDICTIONS_RELPATH = Path("src/biomappings/resources/predictions.sssom.tsv")

# Weight decays with distance: alpha = max(MIN, A0 * DECAY**(dist-1))
A0, DECAY, ALPHA_MIN = 0.7, 0.7, 0.3

COLLECTION = {
    "icd10": {
        "source": "csv",
        "model": "ft",
        "csv_path": "icd10_concepts.tsv",
        "id_prefixes": ["icd10:"],
    }
}
MAPPING = {
    STUDY: {
        "src_collection": "icd10",
        "tgt_collection": "mesh_full",
        "src_col": "subject_id",
        "tgt_col": "object_id",
        "threshold": 0.9,
        "top_k": 1,
        "reverse": False,
    }
}


def _flat(x):
    # flatten nested lists of strings (UMLS nests defs/synonyms for higher-order codes), dropping blanks
    if isinstance(x, str):
        return [x] if x.strip() else []
    if isinstance(x, list):
        return list(chain.from_iterable(_flat(y) for y in x))
    return []


def _norm(s):
    # token-sorted, punctuation-free label form for exact-name comparison
    return " ".join(sorted(re.findall(r"[a-z0-9]+", (s or "").lower())))


def _cosine(remarks):
    m = re.search(r"cosine=([\d.]+)", str(remarks))
    return float(m.group(1)) if m else None


def _run(entry_main, cli_name, argv):
    old = sys.argv
    sys.argv = [cli_name, *argv]
    try:
        entry_main()
    finally:
        sys.argv = old


# Inputs


def ensure_mesh_owl(data_dir):
    """Cache the full MeSH OWL under ~/.data/mesh/ and expose it where leonmap reads it."""
    dst = data_dir / "mesh.owl"
    if dst.exists():
        return dst
    src = pystow.ensure_gunzip("mesh", url=MESH_OWL_GZ_URL, name="mesh.owl.gz")
    data_dir.mkdir(parents=True, exist_ok=True)
    dst.symlink_to(src)
    return dst


def load_semra_sssom():
    """Cache the SemRA disease landscape and return it in raw SSSOM form."""
    path = pystow.ensure_gunzip("semra", url=SEMRA_URL, name=SEMRA_NAME)
    return pl.read_csv(path, separator="\t")


def _umls_definitions():
    raw = map_icd10_to_definitions(umls_api_key=os.environ["UMLS_API_KEY"])
    return {
        code: {
            "definition": next(iter(_flat(v.get("definition"))), ""),
            "synonyms": _flat(v.get("synonyms")),
        }
        for code, v in raw.items()
    }


def load_icd10():
    g = get_icd10_graph()
    children = {
        c: kids
        for c in g.nodes
        if (kids := [u for u, _, d in g.in_edges(c, data=True) if d.get("kind") == "is_a"])
    }
    return g, children


def write_concepts(g, data_dir, use_umls):
    defs = {}
    if use_umls:
        try:
            defs = _umls_definitions()
        except Exception:
            pass
    rows = []
    for code, data in g.nodes(data=True):
        rub = data.get("rubrics", {}) or {}
        label = (rub.get("preferred") or [""])[0].strip() or code
        umls = defs.get(code, {})
        synonyms = (rub.get("inclusion") or []) + (umls.get("synonyms") or [])
        synonyms = [s.strip() for s in synonyms if s.strip() and s.strip().lower() != label.lower()]
        rows.append(
            {
                "id": f"icd10:{code}",
                "label": label,
                "definition": umls.get("definition", ""),
                "synonyms": ";".join(dict.fromkeys(synonyms)),
            }
        )
    data_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(data_dir / "icd10_concepts.tsv", sep="\t", index=False)


def build_collections(g, cfg, args, build_main):
    """Embed whatever is missing. leonmap builds a collection once its spec is registered."""
    db_dir, data_dir = resolve_path(cfg.db_dir), resolve_path(cfg.data_dir)
    raw = db_dir / "icd10" / "index.raw.faiss"

    todo = []
    if args.rebuild or not raw.exists():
        write_concepts(g, data_dir, use_umls=not args.no_umls)
        todo.append("icd10")
    if not (db_dir / "mesh_full" / "index.faiss").exists():
        ensure_mesh_owl(data_dir)
        todo.append("mesh_full")

    if todo:
        _run(build_main, "leonmap-build", ["--collections", *todo, "--monitor", "0", "--rebuild"])
    if "icd10" in todo:
        raw.write_bytes(
            (db_dir / "icd10" / "index.faiss").read_bytes()
        )  # pristine pre-blend snapshot
    return raw


# Hierarchical vector blend


def _blend_pass(vecs, pos, order, neighbors_of):
    dist = {}
    for code in order:
        nbrs = [pos[f"icd10:{c}"] for c in neighbors_of.get(code, []) if f"icd10:{c}" in pos]
        dist[code] = 1 + max((dist.get(c, 0) for c in neighbors_of.get(code, [])), default=-1)
        p = pos.get(f"icd10:{code}")
        if p is None or not nbrs:
            continue
        a = max(ALPHA_MIN, A0 * DECAY ** (dist[code] - 1))
        v = a * vecs[p] + (1 - a) * vecs[nbrs].mean(axis=0)
        vecs[p] = v / (np.linalg.norm(v) or 1.0)
    return vecs


# rewrite the icd10 index: blend every node toward descendants (bottom-up) and ancestors (top-down), then average
def blend_collection(db_dir, children):
    cdir = db_dir / "icd10"
    index = faiss.read_index(str(cdir / "index.raw.faiss"))
    pos = json.loads((cdir / "id2pos.json").read_text())
    vecs = index.reconstruct_n(0, index.ntotal)

    tree = nx.DiGraph((p, c) for p, kids in children.items() for c in kids)
    leaves_first = list(reversed(list(nx.topological_sort(tree))))
    root_first = list(reversed(leaves_first))
    parent_of = {c: [p] for p, kids in children.items() for c in kids}

    down_order = [c for c in root_first if c in children]
    up = _blend_pass(vecs.copy(), pos, leaves_first, children)
    down = _blend_pass(vecs.copy(), pos, down_order, parent_of)
    combined = up + down
    norms = np.linalg.norm(combined, axis=1, keepdims=True)
    blended = combined / np.where(norms == 0, 1.0, norms)

    out = faiss.IndexFlatIP(index.d)
    out.add(blended)
    faiss.write_index(out, str(cdir / "index.faiss"))


# Lexical labeling


def refine_mapping(mapper_tsv, g, cfg):
    # label each baseline top-1 as exact/synonym/semantic via lexical lookup; else it defaults to semantic
    mesh = load_collection(cfg, "mesh_full")

    rows = []
    for _, base in pd.read_csv(mapper_tsv, sep="\t").fillna("").iterrows():
        code = base["src_id"].split(":", 1)[1]
        rub = g.nodes[code].get("rubrics", {}) or {}
        label = base["src_label"] or (rub.get("preferred") or [code])[0]
        lexical = set(mesh.exact_match_ids(label, rub.get("inclusion", [])))
        cos = _cosine(base["remarks"])
        raw = round(min(cos if cos is not None else float(base["score"]), 1.0), 6)
        if base["tgt_id"] in lexical:
            kind = "exact" if _norm(label) == _norm(base["tgt_label"]) else "synonym"
            conf, remark = 1.0, f"{kind};cosine={raw:.6f}"
        else:
            conf, remark = raw, "semantic"
        rows.append(
            {
                "src_id": base["src_id"],
                "src_label": label,
                "tgt_id": base["tgt_id"],
                "tgt_label": base["tgt_label"],
                "rank": 1,
                "score": conf,
                "remarks": remark,
            }
        )

    out = mapper_tsv.with_suffix(".refined.tsv")
    pd.DataFrame(rows).to_csv(out, sep="\t", index=False)
    return out


# Classification + SSSOM


def _predictions_df(tsv):
    d = pd.read_csv(tsv, sep="\t").fillna("")
    d["src"], d["tgt"] = d.src_id.map(canonicalize_id), d.tgt_id.map(canonicalize_id)
    remark = {(s, t): r for s, t, r in zip(d.src, d.tgt, d.remarks, strict=False)}
    frame = pl.DataFrame(
        {
            "source identifier": d.src,
            "source name": d.src_label,
            "source prefix": "icd10",
            "target identifier": d.tgt,
            "target name": d.tgt_label,
            "target prefix": "mesh",
            "confidence": d.score.astype(float),
        }
    )
    return frame, remark


def _to_common(df):
    tid = "predicted identifier" if "predicted identifier" in df.columns else "target identifier"
    tnm = "predicted name" if "predicted name" in df.columns else "target name"
    conf = pl.col("confidence") if "confidence" in df.columns else pl.lit(1.0).alias("confidence")
    return df.select(
        [
            pl.col("source identifier"),
            pl.col("source name"),
            pl.col(tid).alias("target identifier"),
            pl.col(tnm).alias("target name"),
            conf,
        ]
    )


def _provenance(mesh_owl):
    """Column values shared by every row: source releases and tool identity."""
    icd10 = re.search(r"icd10(\d{4})en", ICD10_XML_URL)
    mesh = None
    if mesh_owl.exists():  # absent when mapping against a prebuilt index
        with open(mesh_owl, encoding="utf-8", errors="replace") as f:
            mesh = re.search(r"/resources/mesh/(\d{4})/", f.read(4000))
    return {
        "subject_source_version": icd10.group(1) if icd10 else "",
        "object_source_version": mesh.group(1) if mesh else "",
        "mapping_tool": MAPPING_TOOL,
        "mapping_tool_id": "leonmap",
        "mapping_tool_version": md.version("leonmap"),
        "mapping_date": date.today().isoformat(),
    }


def _write_sssom(df, out_path, remark, provenance):
    # remark is looked up by (src, tgt) since get_right_wrong_mappings drops it as a column
    if df.is_empty():
        return
    stem = out_path.name.removesuffix(".sssom.tsv")
    set_url = (
        "https://github.com/gyorilab/mapnet/blob/main/scripts/"
        f"{out_path.parent.name}/{out_path.name}"
    )
    header = (
        "#curie_map:\n#  icd10: https://icd.who.int/browse10/2019/en#/\n"
        "#  mesh: https://meshb.nlm.nih.gov/record/ui?ui=\n"
        "#  skos: http://www.w3.org/2004/02/skos/core#\n"
        "#  semapv: https://w3id.org/semapv/vocab/\n"
        f"#mapping_set_id: {set_url}\n"
        f"#mapping_set_title: {stem}\n"
        "#mapping_tool: leonmap\n"
    )
    records = []
    for r in df.iter_rows(named=True):
        obj = r.get("predicted identifier", r["target identifier"])
        kind, _, _ = remark.get((r["source identifier"], obj), "semantic").partition(";")
        records.append(
            {
                "subject_id": r["source identifier"],
                "subject_label": r["source name"],
                "predicate_id": "skos:exactMatch" if kind == "exact" else "skos:closeMatch",
                "object_id": obj,
                "object_label": r.get("predicted name", r["target name"]),
                "mapping_justification": "semapv:LexicalMatching"
                if kind in ("exact", "synonym")
                else "semapv:SemanticSimilarityThresholdMatching",
                "confidence": r["confidence"],
                **provenance,
            }
        )
    out = pd.DataFrame(records, columns=SSSOM_COLUMNS).fillna("")
    with open(out_path, "w") as f:
        f.write(header)
    out.to_csv(out_path, sep="\t", index=False, mode="a")


def append_predictions(df, remark, provenance, predictions_path):
    """Append the novel mappings to a Biomappings predictions file."""
    tool = sssom_pydantic.MappingTool(
        name=provenance["mapping_tool"], version=provenance["mapping_tool_version"]
    )
    mappings = []
    for r in df.iter_rows(named=True):
        obj = r.get("predicted identifier", r["target identifier"])
        kind, _, _ = remark.get((r["source identifier"], obj), "semantic").partition(";")
        lexical = kind in ("exact", "synonym")
        mappings.append(
            sssom_pydantic.SemanticMapping(
                subject=curies.NamableReference.from_curie(
                    r["source identifier"], name=r["source name"] or None
                ),
                predicate=curies.NamableReference(
                    prefix="skos", identifier="exactMatch" if kind == "exact" else "closeMatch"
                ),
                object=curies.NamableReference.from_curie(
                    obj, name=r.get("predicted name", r["target name"]) or None
                ),
                justification=curies.Reference(
                    prefix="semapv",
                    identifier="LexicalMatching"
                    if lexical
                    else "SemanticSimilarityThresholdMatching",
                ),
                confidence=r["confidence"],
                mapping_tool=tool,
                subject_source_version=provenance["subject_source_version"] or None,
                object_source_version=provenance["object_source_version"] or None,
                mapping_date=date.today(),
            )
        )

    existing, converter, metadata = sssom_pydantic.read(predictions_path)
    if converter.standardize_prefix("icd10") is None:
        converter = curies.Converter(
            [
                *converter.records,
                curies.Record(prefix="icd10", uri_prefix="https://icd.who.int/browse10/2019/en#/"),
            ]
        )
    sssom_pydantic.write(
        [*existing, *mappings],
        predictions_path,
        metadata=metadata,
        converter=converter,
        drop_duplicates=True,
        sort=True,
    )
    len(sssom_pydantic.read(predictions_path)[0]) - len(existing)


def _biomappings_evidence():
    # icd10:<->mesh: pairs from Biomappings SSSOM exports (read directly; mapnet's own loader expects an old schema)
    frames = []
    for path in (PREDICTIONS_SSSOM_PATH, POSITIVES_SSSOM_PATH):
        d = pd.read_csv(path, comment="#", sep="\t").fillna("")
        d[["subject_id", "object_id"]] = d[["subject_id", "object_id"]].map(canonicalize_id)
        fwd = d[d.subject_id.str.startswith("icd10:") & d.object_id.str.startswith("mesh:")]
        rev = d[d.subject_id.str.startswith("mesh:") & d.object_id.str.startswith("icd10:")].rename(
            columns={
                "subject_id": "object_id",
                "object_id": "subject_id",
                "subject_label": "object_label",
                "object_label": "subject_label",
            }
        )
        frames.append(pd.concat([fwd, rev]))
    ev = pd.concat(frames, ignore_index=True)
    return sssom_to_biomappings(
        pl.from_pandas(ev[["subject_id", "subject_label", "object_id", "object_label"]])
    )


def classify(predictions, remark, out_dir, semra_raw, mesh_owl, predictions_path):
    # flatten n:1 collisions to the best 1:1 pick, split right/wrong/novel against evidence, write SSSOM
    out_dir.mkdir(parents=True, exist_ok=True)

    semra = sssom_to_biomappings(
        semra_raw, {"icd10": {}, "mesh": {}}, {"icd10": "icd10", "mesh": "mesh"}
    )
    predictions = repair_names_with_semra(predictions, semra)

    # collapse n:1 collisions: exact label match beats synonym beats semantic, tie-broken by raw cosine
    kind_rank = {"exact": 2, "synonym": 1, "semantic": 0}

    def quality(r):
        kind, _, comment = remark.get(
            (r["source identifier"], r["target identifier"]), ""
        ).partition(";")
        cos = _cosine(comment)
        if cos is None:
            cos = r["confidence"]
        return kind_rank.get(kind, 0), cos if cos is not None else 0.0

    keep, losers, used_src, used_tgt = [], [], set(), set()
    for r in sorted(predictions.to_dicts(), key=quality, reverse=True):
        s, t = r["source identifier"], r["target identifier"]
        (losers if s in used_src or t in used_tgt else keep).append(r)
        used_src.add(s)
        used_tgt.add(t)
    schema = predictions.schema
    predictions, dup_losers = pl.DataFrame(keep, schema=schema), pl.DataFrame(losers, schema=schema)

    evidence = make_undirected(pl.concat([semra, _biomappings_evidence()]).unique())

    right, wrong, novel = get_right_wrong_mappings(predictions, evidence)
    right, novel = _to_common(right), _to_common(novel)
    wrong = pl.concat([_to_common(wrong), _to_common(dup_losers)])
    provenance = _provenance(mesh_owl)
    for tag, part in (("novel", novel), ("right", right), ("wrong", wrong)):
        _write_sssom(part, out_dir / f"leonmap_{STUDY}_{tag}.sssom.tsv", remark, provenance)
    if predictions_path is not None:
        append_predictions(novel, remark, provenance, predictions_path)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-r", "--rebuild", action="store_true", help="re-embed the icd10 collection")
    ap.add_argument(
        "-t", "--threshold", type=float, default=0.9, help="mapper confidence threshold"
    )
    ap.add_argument(
        "--no-blend",
        action="store_true",
        help="map against the original db (skip the tree re-arrangement)",
    )
    ap.add_argument(
        "--no-umls", action="store_true", help="rebuild without UMLS enrichment (ClaML labels only)"
    )
    ap.add_argument(
        "--no-refine",
        action="store_true",
        help="skip lexical-hit labeling (exact/synonym predicates fall back to semantic)",
    )
    ap.add_argument(
        "--work-dir",
        type=Path,
        default=Path("."),
        help="root for db/, data/, models/, mapper_results/",
    )
    ap.add_argument("--out-dir", default=f"leonmap_{STUDY}_classified")
    ap.add_argument(
        "--predictions-path",
        help=f"Biomappings predictions.sssom.tsv to append to "
        f"(default: {PREDICTIONS_RELPATH} under the working directory)",
    )
    ap.add_argument(
        "--no-append",
        action="store_true",
        help="only write the classified files, don't append to predictions",
    )
    args = ap.parse_args()

    predictions_path = None
    if not args.no_append:
        predictions_path = Path(args.predictions_path or PREDICTIONS_RELPATH).expanduser().resolve()
        if not predictions_path.is_file():
            raise SystemExit(
                f"predictions file not found at {predictions_path}; pass "
                "--predictions-path with the full path to predictions.sssom.tsv"
            )

    root = args.work_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    config.PROJECT_ROOT = root
    from leonmap.build_vdb import main as build_main
    from leonmap.mapper import main as mapper_main

    COLLECTIONS.update(COLLECTION)
    MAPPINGS.update(MAPPING)

    cfg = BuildConfig()
    if not resolve_path(cfg.ft_model_path).exists():
        snapshot_download(repo_id=HF_MODEL_REPO, local_dir=str(resolve_path(cfg.ft_model_path)))

    g, children = load_icd10()
    raw = build_collections(g, cfg, args, build_main)

    semra_raw = load_semra_sssom()

    db_dir = resolve_path(cfg.db_dir)
    if args.no_blend:
        (db_dir / "icd10" / "index.faiss").write_bytes(raw.read_bytes())
    else:
        blend_collection(db_dir, children)

    _run(mapper_main, "leonmap-map", ["--study", STUDY, "--threshold", str(args.threshold)])

    run = max((resolve_path("mapper_results") / STUDY).glob("run_*"), key=lambda p: p.name)
    tsv = run / "icd10_to_mesh_full.tsv"
    if not args.no_refine:
        tsv = refine_mapping(tsv, g, cfg)
    predictions, remark = _predictions_df(tsv)
    classify(
        predictions,
        remark,
        root / args.out_dir,
        semra_raw,
        resolve_path(cfg.data_dir) / "mesh.owl",
        predictions_path,
    )


if __name__ == "__main__":
    main()

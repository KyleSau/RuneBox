"""Structural comparison of decoded RS models."""

from __future__ import annotations

from dataclasses import dataclass, field

from .model_decoder import RSModel


@dataclass
class FieldReport:
    name: str
    status: str  # OK, MISMATCH, unsupported
    detail: str = ""


@dataclass
class CompareReport:
    model_id: int
    fields: list[FieldReport] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(f.status in ("OK", "unsupported") for f in self.fields)

    def format_text(self) -> str:
        lines = [f"Model {self.model_id} roundtrip report"]
        for item in self.fields:
            suffix = f" ({item.detail})" if item.detail else ""
            lines.append(f"{item.name}: {item.status}{suffix}")
        lines.append("")
        lines.append(f"RESULT: {'PASS' if self.passed else 'FAIL'}")
        return "\n".join(lines)


def compare_models(original: RSModel, candidate: RSModel) -> CompareReport:
    report = CompareReport(model_id=original.model_id)

    _compare_count(report, "Vertices", len(original.vertices), len(candidate.vertices))
    _compare_count(report, "Faces", len(original.faces), len(candidate.faces))

    if len(original.vertices) == len(candidate.vertices):
        mismatches = sum(1 for a, b in zip(original.vertices, candidate.vertices) if a != b)
        if mismatches:
            report.fields.append(FieldReport("Vertex coordinates", "MISMATCH", f"{mismatches} differ"))
        else:
            report.fields.append(FieldReport("Vertex coordinates", "OK", f"{len(original.vertices)}/{len(original.vertices)}"))
    else:
        report.fields.append(FieldReport("Vertex coordinates", "MISMATCH", "count differs"))

    if len(original.faces) == len(candidate.faces):
        mismatches = sum(1 for a, b in zip(original.faces, candidate.faces) if a != b)
        if mismatches:
            report.fields.append(FieldReport("Face indices", "MISMATCH", f"{mismatches} differ"))
        else:
            report.fields.append(FieldReport("Face indices", "OK", f"{len(original.faces)}/{len(original.faces)}"))
    else:
        report.fields.append(FieldReport("Face indices", "MISMATCH", "count differs"))

    _compare_optional_list(report, "Face colors", original.face_colors, candidate.face_colors)
    _compare_optional_list(report, "Face render types", original.face_infos, candidate.face_infos)
    _compare_optional_list(report, "Face priorities", original.face_priorities, candidate.face_priorities)
    _compare_global_priority(report, original, candidate)
    _compare_optional_list(report, "Face alpha", original.face_alphas, candidate.face_alphas)
    _compare_optional_list(report, "Vertex skins", original.vertex_skins, candidate.vertex_skins)
    _compare_optional_list(report, "Face skins", original.face_skins, candidate.face_skins)
    _compare_textured_faces(report, original, candidate)

    return report


def _compare_count(report: CompareReport, name: str, orig: int, cand: int) -> None:
    if orig == cand:
        report.fields.append(FieldReport(name, "OK", f"{orig}/{orig}"))
    else:
        report.fields.append(FieldReport(name, "MISMATCH", f"{orig} vs {cand}"))


def _compare_optional_list(
    report: CompareReport,
    name: str,
    original: list | None,
    candidate: list | None,
) -> None:
    if original is None and candidate is None:
        report.fields.append(FieldReport(name, "unsupported"))
        return
    if original is None or candidate is None:
        report.fields.append(FieldReport(name, "MISMATCH", "presence differs"))
        return
    if len(original) != len(candidate):
        report.fields.append(FieldReport(name, "MISMATCH", f"length {len(original)} vs {len(candidate)}"))
        return
    mismatches = sum(1 for a, b in zip(original, candidate) if a != b)
    if mismatches:
        report.fields.append(FieldReport(name, "MISMATCH", f"{mismatches} differ"))
    else:
        report.fields.append(FieldReport(name, "OK"))


def _compare_global_priority(report: CompareReport, original: RSModel, candidate: RSModel) -> None:
    if original.face_priorities is not None or candidate.face_priorities is not None:
        return
    if original.priority == candidate.priority:
        if original.priority >= 0:
            report.fields.append(FieldReport("Global priority", "OK", str(original.priority)))
    else:
        report.fields.append(
            FieldReport("Global priority", "MISMATCH", f"{original.priority} vs {candidate.priority}")
        )


def _compare_textured_faces(report: CompareReport, original: RSModel, candidate: RSModel) -> None:
    if not original.textured_faces and not candidate.textured_faces:
        report.fields.append(FieldReport("Textures", "unsupported"))
        return
    if len(original.textured_faces) != len(candidate.textured_faces):
        report.fields.append(
            FieldReport(
                "Textures",
                "MISMATCH",
                f"{len(original.textured_faces)} vs {len(candidate.textured_faces)} textured faces",
            )
        )
        return
    mismatches = sum(1 for a, b in zip(original.textured_faces, candidate.textured_faces) if a != b)
    if mismatches:
        report.fields.append(FieldReport("Textures", "MISMATCH", f"{mismatches} axis triplets differ"))
    else:
        report.fields.append(FieldReport("Textures", "OK", f"{len(original.textured_faces)} textured faces"))

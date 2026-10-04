from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class UnitKind(str, Enum):
    USER = "user"            # ~/.claude/skills
    PROJECT = "project"      # <repo>/.claude/skills
    PLUGIN = "plugin"        # 透過 marketplace / plugin 安裝
    DIR = "dir"              # 使用者直接指定的資料夾、無 manifest 的 repo（推測）
    MEMORY = "memory"        # CLAUDE.md 這類常駐指令（只參與規則分析）


class Severity(str, Enum):
    ERROR = "error"
    WARN = "warn"
    INFO = "info"


@dataclass
class InstallUnit:
    id: str                  # 例：user、project:C:/repo、plugin:anthropic-agent-skills/document-skills、
                             #     dir:gh:garrytan/gstack
    kind: UnitKind
    label: str               # 人看的名稱
    origin: str              # 來源說明：本機路徑或 gh:owner/repo@sha
    namespaced: bool         # plugin 為 True（skill 名稱前會加 plugin 名稱）
    inferred: bool = False   # 沒有 manifest、靠推測掃描得到時為 True
    priority: int = 0        # 同名遮蔽判斷用，數字大者勝（依 F1）
    skills: list[Skill] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    pack: str = ""           # 發佈單位（同一個 repo / marketplace）；空字串表示等同 id

    @property
    def pack_id(self) -> str:
        return self.pack or self.id


@dataclass
class Rule:
    text: str
    polarity: int            # +1 = 必須／總是，-1 = 禁止／不要
    strength: int            # 1 = 建議（should/盡量），2 = 強制（must/never/必須/禁止）
    topic: frozenset[str]    # 去掉標記詞與停用詞後的主題詞
    line: int                # 在 SKILL.md 中的行號（1 起算）


@dataclass
class FileRef:
    raw: str                 # 原文寫法
    resolved: Path | None    # 解析後的路徑；無法解析為 None
    line: int
    absolute: bool
    exists: bool | None      # 無法判斷時為 None


@dataclass
class Skill:
    id: str                  # f"{unit.id}#{name}"；name 缺失時用資料夾名稱
    name: str                # frontmatter name（缺失時退回資料夾名稱，並記錄 spec 問題）
    qualified_name: str      # namespaced 時為 "plugin:name"，否則等於 name
    description: str
    body: str                # frontmatter 之後的內文
    path: Path               # SKILL.md 的實際位置（stub 解析後）
    dir: Path
    unit_id: str
    frontmatter: dict
    frontmatter_error: str | None
    model_invocable: bool    # disable-model-invocation 為 true 時為 False
    body_line_offset: int    # 內文第一行在檔案中的行號，計算 Rule.line 用
    rules: list[Rule] = field(default_factory=list)
    refs: list[FileRef] = field(default_factory=list)
    suppressions: list[Suppression] = field(default_factory=list)


@dataclass
class Suppression:
    rule: str                # 規則代碼或 "*"
    target: str | None       # 另一個 skill 的 name / qualified_name / id；None 表示全部
    reason: str
    origin: str              # "inline" 或設定檔路徑


@dataclass
class SkillRef:
    skill_id: str
    name: str
    unit_id: str
    path: str
    line: int | None = None
    quote: str | None = None # 原文引用（證據）
    qualified_name: str | None = None


@dataclass
class Finding:
    rule: str                # 規則代碼，見第 8 節
    severity: Severity
    title: str               # 已翻譯好的短標題
    message: str             # 已翻譯好的完整說明
    skills: list[SkillRef]
    evidence: dict           # 規則專屬的數值證據（相似度、共同詞彙、分數…）
    confidence: float        # 0–1
    source: str              # "static" | "llm" | "route"
    fix: str | None = None   # 修正建議
    suppressed_by: str | None = None

    @property
    def fingerprint(self) -> str:
        """穩定識別碼：sha1(rule + 排序後的 skill_id 清單)[:12]。用於快取、CI 比對、白名單。"""
        ids = sorted([s.skill_id for s in self.skills])
        raw = f"{self.rule}:" + ",".join(ids)
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


@dataclass
class ScanResult:
    units: list[InstallUnit]
    findings: list[Finding]
    stats: dict              # 見 10.2
    config_used: dict

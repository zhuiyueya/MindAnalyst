import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.llm.service import LLMService
from src.core.config import settings
from src.services.llm_call_service import LlmCallService
from src.models.models import Author, AuthorReport, ContentItem, Segment, Summary
from src.repositories.segment_repo import SegmentRepository
from src.repositories.summary_repo import SummaryRepository

logger = logging.getLogger(__name__)


class AuthorReportService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.llm = LLMService()
        self.llm_calls = LlmCallService(session)
        self.summaries = SummaryRepository(session)
        self.segments = SegmentRepository(session)

    def _extract_report_version(self, profile_key: Optional[str]) -> str:
        if not profile_key:
            return "v1"
        tail = profile_key.split("/")[-1]
        return tail if tail.startswith("v") else "v1"

    def _build_author_report_markdown(self, raw: Optional[Dict[str, Any]]) -> str:
        if not raw:
            return ""
        existing = raw.get("report_markdown")
        if isinstance(existing, str) and existing.strip():
            return existing

        def _pick(keys: List[str]) -> Any:
            for key in keys:
                if key in raw and raw.get(key) not in (None, ""):
                    return raw.get(key)
            return None

        def _format_scenarios(value: Any) -> str:
            if isinstance(value, list):
                blocks = []
                for item in value:
                    if isinstance(item, dict):
                        scenario = (item.get("scenario") or item.get("scene") or "").strip()
                        trigger = (item.get("trigger") or "").strip()
                        actions = item.get("action_sequence") or []
                        hidden_rules = (item.get("hidden_rules") or "").strip()
                        lines = []
                        if scenario:
                            lines.append(f"### {scenario}")
                        if trigger:
                            lines.append(f"- 触发信号: {trigger}")
                        if hidden_rules:
                            lines.append(f"- 隐形规则: {hidden_rules}")
                        if actions:
                            if isinstance(actions, list):
                                actions_md = "\n".join([f"  - {a}" for a in actions if a])
                                if actions_md:
                                    lines.append("- 动作序列:\n" + actions_md)
                            else:
                                lines.append(f"- 动作序列: {actions}")
                        block = "\n".join(lines).strip()
                        if block:
                            blocks.append(block)
                    else:
                        blocks.append(str(item))
                return "\n\n".join([b for b in blocks if b])
            if value is None:
                return ""
            return str(value).strip()

        def _format_cognitive_foundation(value: Any) -> str:
            if isinstance(value, dict):
                axioms = value.get("axioms") or []
                variables = value.get("fate_variables") or []
                lines = []
                if axioms:
                    axioms_md = "\n".join([f"- {a}" for a in axioms if a])
                    if axioms_md:
                        lines.append("### 核心公理\n" + axioms_md)
                if variables:
                    vars_md = "\n".join([f"- {v}" for v in variables if v])
                    if vars_md:
                        lines.append("### 命运变量\n" + vars_md)
                return "\n\n".join(lines).strip()
            if value is None:
                return ""
            return str(value).strip()

        def _format_paradigm_shifts(value: Any) -> str:
            if isinstance(value, list):
                blocks = []
                for item in value:
                    if isinstance(item, dict):
                        concept = (item.get("concept") or "").strip()
                        common_view = (item.get("common_view") or "").strip()
                        author_view = (item.get("author_view") or "").strip()
                        lines = []
                        if concept:
                            lines.append(f"### {concept}")
                        if common_view:
                            lines.append(f"- 常规认知: {common_view}")
                        if author_view:
                            lines.append(f"- 作者认知: {author_view}")
                        block = "\n".join(lines).strip()
                        if block:
                            blocks.append(block)
                    else:
                        blocks.append(str(item))
                return "\n\n".join([b for b in blocks if b])
            if value is None:
                return ""
            return str(value).strip()

        def _format_action_sop(value: Any) -> str:
            if isinstance(value, list):
                blocks = []
                for item in value:
                    if isinstance(item, dict):
                        trigger = (item.get("trigger_situation") or "").strip()
                        steps = item.get("execution_steps") or ""
                        tools = (item.get("tools_or_scripts") or "").strip()
                        lines = []
                        if trigger:
                            lines.append(f"### {trigger}")
                        if steps:
                            lines.append(f"- 执行步骤: {steps}")
                        if tools:
                            lines.append(f"- 工具/话术: {tools}")
                        block = "\n".join(lines).strip()
                        if block:
                            blocks.append(block)
                    else:
                        blocks.append(str(item))
                return "\n\n".join([b for b in blocks if b])
            if value is None:
                return ""
            return str(value).strip()

        def _format_boundaries(value: Any) -> str:
            if isinstance(value, dict):
                sacrifice = (value.get("required_sacrifice") or "").strip()
                unsuitable = (value.get("unsuitable_audience") or "").strip()
                lines = []
                if sacrifice:
                    lines.append(f"- 必须付出的代价: {sacrifice}")
                if unsuitable:
                    lines.append(f"- 不适合人群: {unsuitable}")
                return "\n".join(lines).strip()
            if value is None:
                return ""
            return str(value).strip()

        def _format_playbook(value: Any) -> str:
            if isinstance(value, list):
                blocks = []
                for item in value:
                    if isinstance(item, dict):
                        scenario = (item.get("scenario") or "").strip()
                        author_view = (item.get("author_view") or "").strip()
                        action = (item.get("do") or "").strip()
                        avoid = (item.get("avoid") or "").strip()
                        lines = []
                        if scenario:
                            lines.append(f"### {scenario}")
                        if author_view:
                            lines.append(f"- 作者立场: {author_view}")
                        if action:
                            lines.append(f"- 行动建议: {action}")
                        if avoid:
                            lines.append(f"- 避免事项: {avoid}")
                        block = "\n".join(lines).strip()
                        if block:
                            blocks.append(block)
                    else:
                        blocks.append(str(item))
                return "\n\n".join([b for b in blocks if b])
            if value is None:
                return ""
            return str(value).strip()

        def _format_critical_tactics(value: Any) -> str:
            if isinstance(value, list):
                blocks = []
                for item in value:
                    if isinstance(item, dict):
                        scenario = (item.get("scenario") or item.get("scene") or "").strip()
                        fake_hope = (
                            item.get("fake_hope")
                            or item.get("fool_think")
                            or item.get("illusion")
                            or ""
                        ).strip()
                        real_move = (item.get("real_move") or item.get("ruthless_move") or "").strip()
                        lines = []
                        if scenario:
                            lines.append(f"### {scenario}")
                        if fake_hope:
                            lines.append(f"- 幻想(坑): {fake_hope}")
                        if real_move:
                            lines.append(f"- 破局招数: {real_move}")
                        block = "\n".join(lines).strip()
                        if block:
                            blocks.append(block)
                    else:
                        blocks.append(str(item))
                return "\n\n".join([b for b in blocks if b])
            if value is None:
                return ""
            return str(value).strip()

        core_thesis = _pick(["core_thesis", "一句话总纲", "总纲", "核心论点"])
        cognitive_foundation = _pick(["cognitive_foundation", "认知基石"])
        core = _pick([
            "core_philosophy",
            "core_survival_logic",
            "core_logic",
            "survival_logic",
            "survival_truth",
            "核心生存逻辑",
            "核心生活逻辑",
            "核心逻辑"
        ])
        core_points = _pick(["core_points", "核心观点", "观点清单"])
        topics = _pick(["main_topics", "主要话题", "topics"]) or []
        daily_playbook = _pick(["daily_playbook", "日常应用", "playbook"])
        practical = _pick([
            "practical_guide",
            "practical_table",
            "avoidance_guide",
            "实战避坑指南",
            "实战指南"
        ])
        critical_tactics = _pick(["critical_tactics", "核心实战策"])
        decision_matrix = _pick(["decision_matrix", "损益对赌表", "损益决策表"])
        scenario_algorithms = _pick(["scenario_algorithms", "场景算法"])
        paradigm_shifts = _pick(["paradigm_shifts", "认知反转点"])
        human_nature_scenarios = _pick(["human_nature_scenarios", "人性场景"])
        action_sop = _pick(["action_sop", "实践SOP", "实战SOP"])
        cost_benefit_table = _pick(["cost_benefit_table", "损益决策表"])
        tactical_actions = _pick(["tactical_actions", "场景反击动作"])
        profit_loss_sheet = _pick(["profit_loss_sheet", "p_l_table", "损益核算表"])
        traps = _pick([
            "thinking_traps",
            "cognitive_poison",
            "认知毒药",
            "思维陷阱"
        ])
        anti_virus = _pick(["anti_virus", "生存补丁"])
        failure_modes = _pick(["failure_modes", "失败模式分析"])
        brain_patches = _pick(["brain_patches", "logic_patches", "强力降智补丁"])
        quick_checks = _pick(["quick_checks", "日常判断口诀", "判断口诀"])
        boundaries_and_costs = _pick(["boundaries_and_costs", "边界与代价"])
        audience = _pick([
            "target_audience",
            "who_should_read",
            "谁该看这个",
            "适合谁看"
        ])
        target_user = _pick(["target_user", "适用人群", "目标人群"])
        power_user = _pick(["power_user", "谁能靠这套活得更好"])
        survival_profile = _pick(["survival_profile", "生存画像"])
        vulnerable_groups = _pick(["vulnerable_groups", "target_victim", "谁在被生吞活剥"])

        core_value = core_thesis if core_thesis is not None else core
        core = (str(core_value).strip() if core_value is not None else "")
        practical = (str(practical).strip() if practical is not None else "")
        audience = (str(audience).strip() if audience is not None else "")

        sections = []
        is_survival_algorithm = any([
            scenario_algorithms,
            critical_tactics,
            decision_matrix,
            cost_benefit_table,
            tactical_actions,
            profit_loss_sheet,
            failure_modes,
            anti_virus,
            brain_patches,
            survival_profile,
            power_user,
            vulnerable_groups
        ])
        if core:
            core_title = (
                "## 一句话总纲"
                if core_thesis is not None
                else "## 底层血实话"
                if raw.get("survival_truth")
                else "## 底层算法"
                if is_survival_algorithm
                else "## 核心生活哲学"
            )
            sections.append(core_title + "\n" + core)

        if core_points:
            if isinstance(core_points, list):
                core_points_md = "\n".join([f"- {p}" for p in core_points if p])
            else:
                core_points_md = str(core_points).strip()
            if core_points_md:
                sections.append("## 核心观点\n" + core_points_md)

        cognitive_md = _format_cognitive_foundation(cognitive_foundation)
        if cognitive_md:
            sections.append("## 认知基石\n" + cognitive_md)

        paradigm_md = _format_paradigm_shifts(paradigm_shifts)
        if paradigm_md:
            sections.append("## 认知反转点\n" + paradigm_md)

        human_md = _format_scenarios(human_nature_scenarios)
        if human_md:
            sections.append("## 人性场景\n" + human_md)

        action_md = _format_action_sop(action_sop)
        if action_md:
            sections.append("## 实战 SOP\n" + action_md)

        topic_items = []
        if isinstance(topics, str):
            topic_items = [topics]
        elif isinstance(topics, list):
            topic_items = [t for t in topics if t]
        playbook_md = _format_playbook(daily_playbook)
        if playbook_md:
            sections.append("## 日常应用\n" + playbook_md)
        else:
            tactics_md = _format_critical_tactics(critical_tactics)
            tactical_md = _format_critical_tactics(tactical_actions)
            scenario_md = _format_scenarios(scenario_algorithms)
            if tactics_md:
                sections.append("## 核心实战策\n" + tactics_md)
            elif tactical_md:
                sections.append("## 场景反击动作\n" + tactical_md)
            elif scenario_md:
                sections.append("## 场景算法\n" + scenario_md)
            elif topic_items:
                topics_md = "\n".join([f"- {t}" for t in topic_items])
                sections.append("## 主要话题\n" + topics_md)

        if quick_checks:
            if isinstance(quick_checks, list):
                checks_md = "\n".join([f"- {c}" for c in quick_checks if c])
            else:
                checks_md = str(quick_checks).strip()
            if checks_md:
                sections.append("## 日常判断口诀\n" + checks_md)

        boundaries_md = _format_boundaries(boundaries_and_costs)
        if boundaries_md:
            sections.append("## 边界与代价\n" + boundaries_md)

        decision_text = (str(decision_matrix).strip() if decision_matrix is not None else "")
        cost_benefit = (str(cost_benefit_table).strip() if cost_benefit_table is not None else "")
        profit_loss = (str(profit_loss_sheet).strip() if profit_loss_sheet is not None else "")
        if decision_text:
            sections.append("## 损益对赌表\n" + decision_text)
        elif profit_loss:
            sections.append("## 损益核算表\n" + profit_loss)
        elif cost_benefit:
            sections.append("## 损益决策表\n" + cost_benefit)
        elif practical:
            sections.append("## 实战指南\n" + practical)

        anti_text = (str(anti_virus).strip() if anti_virus is not None else "")
        brain_text = (str(brain_patches).strip() if brain_patches is not None else "")
        failure_text = (str(failure_modes).strip() if failure_modes is not None else "")
        if anti_text:
            sections.append("## 生存补丁\n" + anti_text)
        elif brain_text:
            sections.append("## 强力降智补丁\n" + brain_text)
        elif failure_text:
            sections.append("## 失败模式分析\n" + failure_text)
        elif traps:
            if isinstance(traps, list):
                traps_md = "\n".join([f"- {t}" for t in traps if t])
            else:
                traps_md = str(traps).strip()
            if traps_md:
                sections.append("## 思维陷阱\n" + traps_md)

        power_text = (str(power_user).strip() if power_user is not None else "")
        survival_text = (str(survival_profile).strip() if survival_profile is not None else "")
        vulnerable_text = (str(vulnerable_groups).strip() if vulnerable_groups is not None else "")
        target_text = (str(target_user).strip() if target_user is not None else "")
        if power_text:
            sections.append("## 谁能靠这套活得更好\n" + power_text)
        elif target_text:
            sections.append("## 适用人群\n" + target_text)
        elif vulnerable_text:
            sections.append("## 谁在被生吞活剥\n" + vulnerable_text)
        elif survival_text:
            sections.append("## 生存画像\n" + survival_text)
        elif audience:
            sections.append("## 适合谁看\n" + audience)

        if not sections:
            return ""

        return "# 作者实战指南\n\n" + "\n\n".join(sections)

    async def generate_author_report(self, author_id: str):
        """
        Generate author-level report from existing summaries.
        """
        logger.info(f"Generating report for author {author_id}...")
        author = await self.session.get(Author, author_id)
        if not author:
            logger.warning("Author not found for report generation.")
            return

        rows = await self.summaries.list_with_content_type_by_author_desc(author_id)

        if not rows:
            logger.warning("No summaries found for author report.")
            return

        content_ids = [summary.content_id for summary, _ in rows if summary.content_id]
        segments_by_content: Dict[str, List[Segment]] = await self.segments.list_for_contents_grouped(content_ids)

        grouped: Dict[str, List[Summary]] = {}
        for summary, content_type in rows:
            key = content_type or "generic"
            grouped.setdefault(key, []).append(summary)

        if author.author_type:
            grouped = {author.author_type: [summary for summary, _ in rows]}

        for content_type, summaries in grouped.items():
            full_context_parts: List[str] = []
            for idx, summary in enumerate(summaries, start=1):
                segs = segments_by_content.get(summary.content_id) or []
                if not segs:
                    continue
                text = "\n".join([s.text for s in segs if s.text]).strip()
                if text:
                    full_context_parts.append(f"视频{idx}全文:\n{text}")
            context_override = "\n\n".join(full_context_parts) if full_context_parts else None

            summary_data = [s.json_data for s in summaries if s.json_data]
            if not summary_data:
                continue

            result = await self.llm.generate_author_report(
                summary_data,
                content_type,
                context_override=context_override
            )
            if result.call:
                await self.llm_calls.record_call_safe(result.call)
            if result.call and result.call.status == "error":
                logger.warning(f"Report generation failed: {result.call.error_message}")
                continue

            raw = result.raw
            report_content = json.dumps(raw, ensure_ascii=False, indent=2) if raw else ""
            report = AuthorReport(
                author_id=author_id,
                content_type=content_type,
                report_type="report.author",
                report_version=self._extract_report_version(result.profile),
                content=report_content,
                json_data={"raw": raw, "profile": result.profile, "content_type": result.content_type}
            )
            self.session.add(report)

        await self.session.commit()
        logger.info(f"Saved author reports for {author_id}")

    async def generate_category_reports_for_author(self, author_id: str) -> Dict[str, Any]:
        logger.info("Generating category reports for author %s", author_id)
        author = await self.session.get(Author, author_id)
        if not author:
            logger.warning("Category reports early return: author_not_found author_id=%s", author_id)
            return {"error": "author_not_found"}

        content_type = author.author_type or "generic"
        categories = [str(x) for x in (author.category_list or []) if str(x).strip()]
        if not categories:
            logger.warning(
                "Category reports early return: category_list_empty author_id=%s content_type=%s",
                author_id,
                content_type,
            )
            return {"error": "category_list_empty"}

        logger.info(
            "Category reports preflight: author_id=%s content_type=%s categories=%s",
            author_id,
            content_type,
            len(categories),
        )

        rows = await self.summaries.list_structured_with_content_by_author_desc(author_id)
        if not rows:
            logger.warning(
                "Category reports early return: no_summaries author_id=%s content_type=%s",
                author_id,
                content_type,
            )
            return {"error": "no_summaries"}

        logger.info(
            "Category reports fetched summaries: author_id=%s row_count=%s",
            author_id,
            len(rows),
        )

        latest_by_content: Dict[str, tuple[Summary, ContentItem]] = {}
        for summary, content in rows:
            if summary.content_id and summary.content_id not in latest_by_content:
                latest_by_content[summary.content_id] = (summary, content)

        logger.info(
            "Category reports latest summaries: author_id=%s latest_by_content=%s",
            author_id,
            len(latest_by_content),
        )

        summaries_by_category: Dict[str, List[tuple[Summary, ContentItem]]] = {c: [] for c in categories}
        for summary, content in latest_by_content.values():
            cat = (summary.video_category or "").strip() if summary.video_category else ""
            if not cat:
                continue
            if cat not in summaries_by_category:
                continue
            if not summary.content:
                continue
            summaries_by_category[cat].append((summary, content))

        logger.info(
            "Category reports grouped: author_id=%s category_nonempty=%s/%s",
            author_id,
            sum(1 for c in categories if summaries_by_category.get(c)),
            len(categories),
        )

        generated = 0
        skipped = 0
        for idx_category, category in enumerate(categories, start=1):
            items = summaries_by_category.get(category) or []
            if not items:
                skipped += 1
                logger.info(
                    "Category report batch skipped (no items): author_id=%s category=%s batch=%s/%s",
                    author_id,
                    category,
                    idx_category,
                    len(categories),
                )
                continue

            logger.info(
                "Category report batch start: author_id=%s category=%s batch=%s/%s video_count=%s",
                author_id,
                category,
                idx_category,
                len(categories),
                len(items),
            )

            context_parts: List[str] = []
            for idx, (summary, content) in enumerate(items, start=1):
                title = (content.title or "").strip()
                header = f"视频{idx}: {title}" if title else f"视频{idx}"
                context_parts.append(f"{header}\n{summary.content}")
            context_override = "\n\n".join([x for x in context_parts if x]).strip()
            if not context_override:
                skipped += 1
                logger.info(
                    "Category report batch skipped (empty context): author_id=%s category=%s batch=%s/%s video_count=%s",
                    author_id,
                    category,
                    idx_category,
                    len(categories),
                    len(items),
                )
                continue

            started_at = time.monotonic()
            try:
                result = await self.llm.generate_author_report([], content_type, context_override=context_override)
            except Exception as exc:
                skipped += 1
                elapsed_ms = int((time.monotonic() - started_at) * 1000)
                logger.error(
                    "Category report batch failed: author_id=%s category=%s batch=%s/%s video_count=%s elapsed_ms=%s error=%s",
                    author_id,
                    category,
                    idx_category,
                    len(categories),
                    len(items),
                    elapsed_ms,
                    exc,
                )
                continue

            if result.call:
                await self.llm_calls.record_call_safe(result.call)
            if result.call and result.call.status == "error":
                skipped += 1
                elapsed_ms = int((time.monotonic() - started_at) * 1000)
                logger.warning(
                    "Category report batch returned error: author_id=%s category=%s batch=%s/%s video_count=%s elapsed_ms=%s result=%s",
                    author_id,
                    category,
                    idx_category,
                    len(categories),
                    len(items),
                    elapsed_ms,
                    result.raw,
                )
                continue

            raw = result.raw
            report_content = json.dumps(raw, ensure_ascii=False, indent=2) if raw else ""

            report = AuthorReport(
                author_id=author_id,
                content_type=content_type,
                report_type="report.author.category",
                report_version=self._extract_report_version(result.profile),
                content=report_content,
                json_data={
                    "category": category,
                    "video_count": len(items),
                    "llm_result": {"raw": raw, "profile": result.profile, "content_type": result.content_type},
                },
            )
            self.session.add(report)
            await self.session.commit()
            generated += 1

            elapsed_ms = int((time.monotonic() - started_at) * 1000)
            logger.info(
                "Category report batch saved: author_id=%s category=%s batch=%s/%s video_count=%s elapsed_ms=%s generated=%s skipped=%s",
                author_id,
                category,
                idx_category,
                len(categories),
                len(items),
                elapsed_ms,
                generated,
                skipped,
            )

        return {"generated": generated, "skipped": skipped, "categories": categories}

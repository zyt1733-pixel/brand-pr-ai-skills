from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ContentPublicationRiskSkillPackageTest(unittest.TestCase):
    def read(self, relative_path: str) -> str:
        return (ROOT / relative_path).read_text(encoding="utf-8")

    def test_包含可直接发布到_github_的完整文件(self) -> None:
        required_files = [
            "SKILL.md",
            "README.md",
            "agents/openai.yaml",
            "references/content-risk-taxonomy.md",
            "references/visual-and-rights-checklist.md",
            "references/review-output.md",
            ".github/workflows/validate.yml",
        ]
        for relative_path in required_files:
            self.assertTrue((ROOT / relative_path).is_file(), f"缺少文件：{relative_path}")

    def test_skill_frontmatter_名称与触发说明完整(self) -> None:
        skill = self.read("SKILL.md")
        self.assertTrue(skill.startswith("---\n"), "SKILL.md 必须包含 YAML frontmatter")
        self.assertRegex(skill, r"(?m)^name: content-publication-risk-review$")
        self.assertRegex(skill, r"(?m)^description: .+发布前.+风险审查.+$")
        self.assertIn("能不能发", skill)
        self.assertIn("不替代", skill)

    def test_skill_引用三份按需规则文件(self) -> None:
        skill = self.read("SKILL.md")
        for reference in [
            "references/content-risk-taxonomy.md",
            "references/visual-and-rights-checklist.md",
            "references/review-output.md",
        ]:
            self.assertIn(reference, skill)

    def test_风险库覆盖舆情黑洞的全部主要风险描述(self) -> None:
        taxonomy = self.read("references/content-risk-taxonomy.md")
        required_terms = [
            "国家统一", "地图", "国家领导人", "人民币", "英雄烈士", "民族", "宗教", "敏感时间点",
            "地域", "城乡", "职业", "性别", "婚姻", "生育", "LGBT", "明星", "宠物",
            "字体", "图片", "音乐", "影视", "原创", "肖像", "隐私",
            "色情", "暴力", "赌博", "迷信", "伪科学", "未成年人", "恶搞",
            "虚构", "数据", "产品功效", "计划", "员工", "高管", "热点", "灾难", "公共秩序",
        ]
        for term in required_terms:
            self.assertIn(term, taxonomy, f"风险库缺少：{term}")

    def test_输出包含四级结论和传播四镜(self) -> None:
        combined = self.read("SKILL.md") + self.read("references/review-output.md")
        for conclusion in ["可以发布", "修改后发布", "暂缓发布，先核实", "高风险，不建议发布"]:
            self.assertIn(conclusion, combined)
        for lens in ["普通受众", "相关群体", "截图传播", "媒体与对立方"]:
            self.assertIn(lens, combined)

    def test_不包含具体品牌案例或案例链接(self) -> None:
        content = "\n".join(
            self.read(path)
            for path in [
                "SKILL.md",
                "references/content-risk-taxonomy.md",
                "references/visual-and-rights-checklist.md",
                "references/review-output.md",
            ]
        )
        banned_identifiers = [
            "美团", "江南布衣", "卫龙", "Ulike", "得物", "刘德华", "苏炳添",
            "copy-lens-review", "copy_lens_review.py",
        ]
        for identifier in banned_identifiers:
            self.assertNotIn(identifier, content, f"不应包含具体案例或外部 Skill 标识：{identifier}")
        self.assertIsNone(re.search(r"https?://", content), "规则文件不应包含案例链接")

    def test_不使用机械综合评分代替专业判断(self) -> None:
        content = self.read("SKILL.md") + self.read("references/review-output.md")
        self.assertIsNone(re.search(r"综合风险分\s*[:：]", content))
        self.assertNotIn("/100", content)
        self.assertIn("单一重大风险", content)

    def test_openai_界面元数据可被识别(self) -> None:
        metadata = self.read("agents/openai.yaml")
        self.assertIn('display_name: "内容发布风险审查"', metadata)
        self.assertIn('$content-publication-risk-review', metadata)
        self.assertIn("allow_implicit_invocation: true", metadata)


if __name__ == "__main__":
    unittest.main()

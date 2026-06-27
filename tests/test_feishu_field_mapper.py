# -*- coding: utf-8 -*-

import hashlib

from integrations.field_mapper import map_record_to_feishu_fields


def test_map_xhs_note_to_feishu_fields():
    record = {
        "platform": "xhs",
        "source_keyword": "编程副业",
        "title": "普通人如何找到编程副业",
        "desc": "我想找一个稳定的编程副业，需要有人指导接单、报价和交付流程。",
        "note_url": "https://www.xiaohongshu.com/explore/note123",
        "time": 1700000000,
        "add_ts": 1700000100,
    }

    fields = map_record_to_feishu_fields(record)

    assert fields is not None
    assert fields["需求标题"] == "普通人如何找到编程副业"
    assert fields["来源平台"] == "xhs"
    assert fields["关键词"] == "编程副业"
    assert "稳定的编程副业" in fields["原文内容"]
    assert fields["来源链接"] == "https://www.xiaohongshu.com/explore/note123"
    assert fields["发布时间"] == 1700000000
    assert fields["采集时间"] == 1700000100
    assert fields["需求类型"] == "未分类"
    assert fields["优先级"] == "中"
    assert fields["状态"] == "待处理"
    expected_hash = hashlib.sha256(
        ("xhs" + record["note_url"] + fields["原文内容"]).encode("utf-8")
    ).hexdigest()
    assert fields["内容哈希"] == expected_hash


def test_map_comment_record_uses_comment_content_and_source_url():
    record = {
        "platform": "dy",
        "keyword": "AI工具",
        "comment": "有没有适合新手做短视频脚本的AI工具，最好可以直接生成分镜。",
        "aweme_id": "734567",
        "share_url": "https://www.douyin.com/video/734567",
        "create_time": 1700000200,
    }

    fields = map_record_to_feishu_fields(record)

    assert fields is not None
    assert fields["来源平台"] == "dy"
    assert fields["来源链接"] == "https://www.douyin.com/video/734567"
    assert fields["原文内容"] == record["comment"]
    assert fields["需求标题"].startswith("有没有适合新手")
    assert fields["发布时间"] == 1700000200


def test_map_record_skips_short_chinese_content():
    record = {
        "platform": "xhs",
        "title": "求推荐",
        "desc": "好用吗",
        "note_url": "https://www.xiaohongshu.com/explore/short",
    }

    assert map_record_to_feishu_fields(record) is None


def test_map_record_infers_platform_and_url_from_known_fields():
    record = {
        "source_keyword": "考研资料",
        "title": "需要一份完整的考研复习资料清单",
        "content": "准备考研但是不知道资料怎么买，希望有人整理公共课和专业课资料清单。",
        "note_url": "https://www.xiaohongshu.com/explore/note456",
    }

    fields = map_record_to_feishu_fields(record)

    assert fields is not None
    assert fields["来源平台"] == "xhs"
    assert fields["来源链接"] == record["note_url"]

"""
AtCoder ABC コンテスト告知自動化スクリプト

1. AtCoderから次のABCコンテスト情報を取得
2. 当日ならSlackに告知メッセージを送信
"""

import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from html.parser import HTMLParser

SLACK_WEBHOOK_URL = os.environ["SLACK_WEBHOOK_URL"]

JST = timezone(timedelta(hours=9))


# --- AtCoder からコンテスト情報取得 ---

class ContestParser(HTMLParser):
    """AtCoderのコンテスト一覧ページからABCコンテストを抽出する"""

    def __init__(self):
        super().__init__()
        self.contests = []
        self._in_upcoming = False
        self._in_td = False
        self._td_count = 0
        self._current_row = {}
        self._capture_text = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "h3":
            self._capture_text = True
            self._captured = ""
        if tag == "tr" and self._in_upcoming:
            self._td_count = 0
            self._current_row = {}
        if tag == "td" and self._in_upcoming:
            self._td_count += 1
            self._in_td = True
            self._td_text = ""
        if tag == "a" and self._in_td and self._td_count == 2:
            href = attrs_dict.get("href", "")
            if "/contests/" in href:
                self._current_row["contest_id"] = href.split("/contests/")[-1]
                self._current_row["url"] = "https://atcoder.jp" + href

    def handle_data(self, data):
        if self._capture_text:
            self._captured += data
        if self._in_td:
            self._td_text += data

    def handle_endtag(self, tag):
        if tag == "h3" and self._capture_text:
            self._capture_text = False
            if "Upcoming" in self._captured:
                self._in_upcoming = True
            elif self._in_upcoming:
                self._in_upcoming = False
        if tag == "td" and self._in_td:
            self._in_td = False
            if self._td_count == 1:
                self._current_row["time_str"] = self._td_text.strip()
        if tag == "tr" and self._in_upcoming and self._current_row.get("contest_id"):
            self.contests.append(self._current_row)


def fetch_next_abc():
    """AtCoderから次のABCコンテスト情報を取得"""
    url = "https://atcoder.jp/contests/"
    req = urllib.request.Request(url, headers={"User-Agent": "ABC-Notify-Bot/1.0"})
    with urllib.request.urlopen(req) as res:
        html = res.read().decode("utf-8")

    parser = ContestParser()
    parser.feed(html)

    abc_contests = [
        c for c in parser.contests
        if re.match(r"abc\d+", c.get("contest_id", ""))
    ]

    if not abc_contests:
        return None

    contest = abc_contests[0]

    time_str = contest["time_str"]
    for fmt in ["%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d %H:%M:%S"]:
        try:
            dt = datetime.strptime(time_str, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=JST)
            contest["datetime"] = dt
            break
        except ValueError:
            continue

    return contest


# --- Slack メッセージ送信 ---

def send_slack_message(contest):
    """Slackに告知メッセージを送信"""
    dt = contest["datetime"]
    date_str = f"{dt.month}/{dt.day}"
    time_str = f"{dt.hour}時"
    if dt.minute:
        time_str += f"{dt.minute}分"
    contest_id = contest["contest_id"]
    contest_num = contest_id.upper()

    message = (
        f"本日（{date_str}）、{time_str}から{contest_num}が開催されます。\n"
        f"出られそうな人はぜひ参加してみてください!!\n"
        f"\n"
        f"https://atcoder.jp/contests/{contest_id}\n"
        f"\n"
        f"結果や感想のNotionページは後日更新する予定です。"
    )

    payload = json.dumps({"text": message}).encode("utf-8")
    req = urllib.request.Request(
        SLACK_WEBHOOK_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req) as res:
        return res.read().decode("utf-8")


# --- メイン ---

def main():
    dry_run = "--dry-run" in sys.argv
    # 12時のcron(0 3 * * *)ならチェックのみ、20時のcron(0 11 * * *)なら送信
    trigger_cron = os.environ.get("TRIGGER_CRON", "")
    check_only = trigger_cron == "0 3 * * *"

    print("AtCoderからコンテスト情報を取得中...")
    contest = fetch_next_abc()

    if not contest:
        print("予定されているABCコンテストが見つかりませんでした。")
        sys.exit(0)

    contest_id = contest["contest_id"]
    dt = contest["datetime"]
    print(f"次のABC: {contest_id} ({dt.strftime('%Y-%m-%d %H:%M')})")

    # 当日チェック
    today = datetime.now(JST).date()
    contest_date_jst = dt.astimezone(JST).date()
    if today != contest_date_jst:
        print(f"今日({today})はコンテスト開催日({contest_date_jst})ではありません。")
        sys.exit(0)

    if check_only:
        print(f"本日{contest_id.upper()}が開催予定です（チェックのみ、送信は20時）")
        return

    if dry_run:
        print("\n[dry-run] 以下のメッセージが送信されます:\n")
        date_str = f"{dt.month}/{dt.day}"
        time_str = f"{dt.hour}時"
        contest_num = contest_id.upper()
        print(f"本日（{date_str}）、{time_str}から{contest_num}が開催されます。")
        print("出られそうな人はぜひ参加してみてください!!")
        print(f"\nhttps://atcoder.jp/contests/{contest_id}")
        print(f"\n結果や感想のNotionページは後日更新する予定です。")
        return

    print("Slackに送信中...")
    result = send_slack_message(contest)
    print(f"Slack送信結果: {result}")
    print("完了!")


if __name__ == "__main__":
    main()

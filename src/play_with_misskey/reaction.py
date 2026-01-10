#!/usr/bin/env python
# coding: utf-8

import requests
import pandas as pd
from tqdm.auto import tqdm
from time import sleep
import schedule
import argparse
import json
from connect_sqlite import save_to_db, get_data
import datetime
from logging import basicConfig, INFO, info, error

basicConfig(
    filename="reaction.log",
    level=INFO,
    format="%(asctime)s - %(levelname)s:%(name)s - %(message)s",
)

args = None


def read_config(path):
    """設定ファイルを読み込んでJSON形式で返す

    Args:
        path (str): 設定ファイルのパス

    Returns:
        dict: 設定情報
    """
    with open(path, "rb") as f:
        config = json.load(f)
    return config


def get_result(endpoint, params, host, header):
    """Misskey APIへPOSTリクエストを送信する

    Args:
        endpoint (str): APIエンドポイント
        params (dict): リクエストパラメータ
        host (str): ホストURL
        header (dict): リクエストヘッダ

    Returns:
        requests.Response: APIレスポンス
    """
    result = requests.post(host + endpoint, headers=header, json=params)
    return result


def get_note():
    """ユーザーのノート(投稿)をMisskey APIから取得し、DBに保存する

    新規のノートのみを抽出してデータベースに追加される。
    タイムゾーンはAsia/Tokyoに統一される。

    Raises:
        requests.exceptions.JSONDecodeError: APIレスポンスがJSON形式でない場合
    """
    info("Start getting note")
    # 設定情報取得
    config = read_config("config.json")
    misskeyio_config = config["misskey.io"]

    # ノート取得
    endpoint = "users/notes"
    params = {
        "i": misskeyio_config["token"],
        "userId": misskeyio_config["my_userid"],
        "limit": 100,  # max 100
        "includeMyRenotes": False,
    }
    try:
        result2 = get_result(
            endpoint, params, misskeyio_config["host"], misskeyio_config["header"]
        )
        result_parse = result2.json()
    except requests.exceptions.JSONDecodeError as e:
        error(e)
        raise e

    # DataFrameにparseする
    notelist = list()
    for note in tqdm(result_parse, desc="Getting note..."):
        text = note["text"]
        if text is None:
            continue
        noteid = note["id"]
        timestamp = note["createdAt"]
        notelist.append([text, noteid, timestamp])
    notelist = pd.DataFrame(notelist, columns=["text", "noteid", "timestamp"])
    notelist["timestamp"] = pd.to_datetime(
        notelist["timestamp"], utc=True
    ).dt.tz_convert("Asia/Tokyo")

    # 保存していないもののみを抽出する
    noteidlist = get_data("misskey.sqlite", "select distinct noteid from notelist")
    notelist = notelist[~notelist["noteid"].isin(noteidlist["noteid"].tolist())]
    save_to_db("misskey.sqlite", notelist, "notelist", if_exists="append", index=False)


def get_reaction(th: int):
    """最新のノートのリアクション情報をAPIから取得し、DBに保存する

    Args:
        th (int): 取得対象とするノート数(最新のth件)

    リアクション情報のうち、未保存のもののみを抽出して追加される。
    APIレスポンスエラーはログに記録されるが、処理は継続される。
    """
    info("Start to get reaction")
    # 設定情報取得
    config = read_config("config.json")
    misskeyio_config = config["misskey.io"]

    reactionlist = list()
    endpoint = "notes/reactions"

    # 最新のth件分のノートを取得する
    noteidlist = get_data(
        "misskey.sqlite",
        f"select distinct noteid from notelist order by timestamp desc limit {th}",
    )

    for noteid in tqdm(noteidlist["noteid"].tolist(), desc="Getting reaction..."):
        params = {
            "i": misskeyio_config["token"],
            "noteId": noteid,
        }
        try:
            response = get_result(
                endpoint, params, misskeyio_config["host"], misskeyio_config["header"]
            )
            if len(response.json()) > 0:
                for reaction in response.json():
                    userid = reaction["user"]["id"]
                    username = reaction["user"]["username"]
                    host = reaction["user"]["host"]
                    reactionlist.append([noteid, userid, username, host])
            sleep(1)
        except requests.exceptions.JSONDecodeError as e:
            error(e)

    reactionlist = pd.DataFrame(
        reactionlist, columns=["noteid", "userid", "username", "host"]
    ).fillna({"host": "misskey.io"})

    # 保存していないリアクションのみを抽出する
    reactionlist_all = get_data(
        "misskey.sqlite", "select distinct noteid, userid from reactionlist"
    )
    reactionlist_all = reactionlist.merge(
        reactionlist_all, how="outer", on=["noteid", "userid"], indicator=True
    )
    reactionlist_all = reactionlist_all.query("_merge=='left_only'")[
        ["noteid", "userid", "username", "host"]
    ]
    save_to_db(
        "misskey.sqlite",
        reactionlist_all,
        "reactionlist",
        if_exists="append",
        index=False,
    )


def following_user(th: int):
    """過去1週間のリアクション数が閾値以上のユーザーをフォローする

    Args:
        th (int): フォロー対象となるリアクション数の閾値

    複数のMistkeyインスタンス(misskey.io, misskey.cloud)でフォローが実行される。
    """
    info("Start to follow users")
    # 直近1週間のノートのリアクション数を集計
    now = datetime.datetime.now()
    span = datetime.timedelta(days=7)
    start_date = (now - span).strftime("%Y-%m-%d")
    reactionlist = get_data(
        "misskey.sqlite",
        f"""
        select
            note.noteid,
            note.timestamp,
            note.text,
            react.userid,
            react.username,
            react.host
        from reactionlist as react
        left join notelist as note
        on note.noteid = react.noteid
        where
            timestamp >= '{start_date}'
        order by timestamp
        """,
    )
    # 設定情報取得
    config = read_config("config.json")
    misskeyio_config = config["misskey.io"]

    # ユーザーをフォローする
    followuserlist = reactionlist.value_counts(subset="userid")
    followuserlist = followuserlist[followuserlist > th].index.tolist()

    endpoint = "following/create"
    pbar = tqdm(followuserlist, desc="following")

    misskeycl_config = config["misskey.cloud"]
    follow_num = 0
    for userId in pbar:
        params = {"i": misskeyio_config["token"], "userId": userId}
        result = get_result(
            endpoint, params, misskeyio_config["host"], misskeyio_config["header"]
        )
        if result.status_code == 200:
            follow_num += 1

        params = {"i": misskeycl_config["token"], "userId": userId}
        result = get_result(
            endpoint, params, misskeycl_config["host"], misskeycl_config["header"]
        )
        if result.status_code == 200:
            follow_num += 1
        pbar.set_postfix(userid=userId, followed_num=follow_num)
        sleep(1)


def add_users_into_list():
    """リアクション数が多いユーザーをリストに追加する

    リアクション数の全体に対する割合が2%以上のユーザーが対象となる。
    除外対象のユーザーIDは設定ファイルで指定可能。
    """
    # 設定情報取得
    config = read_config("config.json")
    misskeyio_config = config["misskey.io"]
    exclude_userids = config.get("exclude_userids", [])
    exclude_condition = "', '".join(exclude_userids) if exclude_userids else ""
    exclude_where = (
        f"userid not in ('{exclude_condition}')" if exclude_condition else ""
    )

    reaction_count = get_data(
        "misskey.sqlite",
        f"""
            select
                userid,
                username,
                count(noteid) as num
            from reactionlist
            where
                {exclude_where}
            group by userid, username
            order by num desc
        """,
    )
    reaction_count["percent"] = reaction_count["num"] / reaction_count["num"].sum()

    target_list_id = misskeyio_config["target_list_id"]

    # リストに追加する
    target_userid_list = reaction_count.query("percent >= 0.02")["userid"].tolist()
    endpoint = "users/lists/push"
    pbar = tqdm(target_userid_list, desc="Adding user into list...")
    added_user_num = 0
    for userid in pbar:
        params = {
            "i": misskeyio_config["token"],
            "userId": userid,
            "listId": target_list_id,
        }
        result = get_result(
            endpoint, params, misskeyio_config["host"], misskeyio_config["header"]
        )

        if result.status_code == 200:
            added_user_num += 1

        pbar.set_postfix(added_user_num=added_user_num)
        sleep(1)


def main(args):
    """メイン処理を実行する

    Args:
        args (argparse.Namespace): コマンドライン引数
    """
    get_note()
    get_reaction(int(args.reaction_th))
    following_user(int(args.follow_th))
    add_users_into_list()


schedule.every().saturday.at("13:00").do(main, args=args)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-m", "--monitor", help="Monitoring mode", action="store_true", dest="monitor"
    )
    parser.add_argument(
        "-rth",
        "--reaction_th",
        help="Threshold of reaction number",
        dest="reaction_th",
        default=100,
    )
    parser.add_argument(
        "-fth",
        "--follow_th",
        help="Threashold of follow number",
        dest="follow_th",
        default=5,
    )
    args = parser.parse_args()

    info(f"Start (Mode:{args.monitor}, [{args.reaction_th}, {args.follow_th}])")
    if args.monitor:
        while True:
            schedule.run_pending()
            sleep(1)
    else:
        main(args)

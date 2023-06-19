#!/usr/bin/env python
# coding: utf-8

import requests
import pandas as pd
from tqdm.auto import tqdm
from time import sleep
import schedule
import argparse
import json
from save_sqlite import save_to_db


def read_config(path):
    with open(path, "rb") as f:
        config = json.load(f)
    return config


def get_result(endpoint, params, host, header):
    result = requests.post(
        host + endpoint,
        headers=header,
        json=params
    )
    return result


def get_note():
    # 設定情報取得
    config = read_config("config.json")
    misskeyio_config = config["misskey.io"]

    # ノート取得
    endpoint = "users/notes"
    params = {
        "i": misskeyio_config["token"],
        "userId": misskeyio_config["my_userid"],
        "limit": 100,   # max 100
        "includeMyRenotes": False,
    }
    result2 = get_result(endpoint, params, misskeyio_config["host"], misskeyio_config["header"])

    notelist = list()
    for note in tqdm(result2.json(), desc="Getting note..."):
        text = note["text"]
        noteid = note["id"]
        notelist.append([text, noteid])
    notelist = pd.DataFrame(notelist, columns=["text", "noteid"])
    save_to_db("misskey.sqlite", notelist, "notelist", if_exists="append")

    return notelist


def get_reaction(notelist):
    # 設定情報取得
    config = read_config("config.json")
    misskeyio_config = config["misskey.io"]

    reactionlist = list()
    endpoint = "notes/reactions"

    for i, note in tqdm(notelist.iterrows(), total=len(notelist), desc="Getting reaction..."):
        noteid = note["noteid"]
        params = {
            "i": misskeyio_config["token"],
            "noteId": noteid,
        }
        response = get_result(endpoint, params, misskeyio_config["host"], misskeyio_config["header"])
        if len(response.json()) > 0:
            for reaction in response.json():
                note = noteid
                userId = reaction["user"]["id"]
                username = reaction["user"]["username"]
                host = reaction["user"]["host"]
                reactionlist.append([noteid, userId, username, host])
        sleep(0.2)
    reactionlist = pd.DataFrame(
        reactionlist,
        columns=["noteid", "userid", "username", "host"]
    ).fillna({"host": "misskey.io"})

    save_to_db("misskey.sqlite", reactionlist, "reactionlist", if_exists="append")

    return reactionlist


def following_user(reactionlist, th: int):
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
        # pbar.set_description(userId)
        params = {
            "i": misskeyio_config["token"],
            "userId": userId
        }
        result = get_result(endpoint, params, misskeyio_config["host"], misskeyio_config["header"])
        if result.status_code == 200:
            follow_num += 1

        params = {
            "i": misskeycl_config["token"],
            "userId": userId
        }
        result = get_result(endpoint, params, misskeycl_config["host"], misskeycl_config["header"])
        if result.status_code == 200:
            follow_num += 1
        pbar.set_postfix(userid=userId, followed_num=follow_num)
        sleep(2)


def main(th=2):
    notelist = get_note()
    reactionlist = get_reaction(notelist)
    following_user(reactionlist, th)


schedule.every().saturday.at("13:00").do(main)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-m", "--monitor",
        help="Monitoring mode",
        action="store_true",
        dest="monitor"
    )
    parser.add_argument(
        "-th", "--threshold",
        help="Threshold value of reaction",
        dest="th",
        default=2
    )
    args = parser.parse_args()
    if args.monitor:
        while True:
            schedule.run_pending()
            sleep(1)
    else:
        main(int(args.th))
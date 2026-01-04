from connect_sqlite import get_data
from plotly import express as px


def plot_reaction_histogram():
    # get data
    df = get_data(
        "misskey.sqlite",
        """
            select
                username.username,
                reaction.num
            from (
                select
                    userid,
                    count(noteid) as num
                from
                    reactionlist
                where
                    userid not in ('7rkr3b1c1c', '82qrp4qp16')
                group by userid
            ) as reaction
            left join (
                select distinct
                    userid,
                    username
                from
                    reactionlist
            ) as username
            on reaction.userid = username.userid
            order by num desc
            ;
        """
    )
    plot = px.histogram(
        df,
        x="username",
        y="num",
        height=700,
        title="リアクション数"
    )
    plot.write_html("output/reaction_histogram.html")


def main():
    plot_reaction_histogram()


if __name__ == "__main__":
    main()

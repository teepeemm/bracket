""" Perform calculations specific to the paper and presentation. """

import collections
import itertools
import json
import math
import typing

import numpy  # type: ignore
import pandas  # type: ignore

import analyze


def get_team_performance(group: str, tourney: str, team: str) -> None:
    """ Summarize how a team has performed within a specific tournament.
    :param group:
    :param tourney:
    :param team: """
    with open('tourneys.json', encoding='utf-8') as json_file:
        tourneys = json.load(json_file)
    description = analyze.SubgroupDesc(**tourneys[group][tourney])._replace(
        group=group, tourney=tourney, directory=f'{group}/{tourney}',
        suffix=tourneys[group].get('suffix', None),
        is_national=tourney in tourneys[group].get('nonconference', (tourney,)))
    win_loss_seeds: dict[str, collections.Counter] = {
        'wins': collections.Counter(),
        'losses': collections.Counter()
    }
    for year in analyze.get_years(description.years):
        for game in analyze.get_game(description, year):
            if game[0].team == team:
                win_loss_seeds['wins'][game[1].seed-game[0].seed] += 1
            if game[1].team == team:
                win_loss_seeds['losses'][game[0].seed-game[1].seed] += 1
    for diff, count in win_loss_seeds['wins'].items():
        print(rf'\addplot[dots]({diff},1)node[{"below"if(diff%2)else"above"}]{{\tiny{count}}};')
    for diff, count in win_loss_seeds['losses'].items():
        print(rf'\addplot[dots]({diff},0)node[{"above"if(diff%2)else"below"}]{{\tiny{count}}};')
    for k, v in win_loss_seeds.items():
        print(sum(v.values()), k, v.items())
    win_loss_seeds_with_list = {k: list(v.elements()) for k, v in win_loss_seeds.items()}
    print(analyze.calc_log_reg(win_loss_seeds_with_list))


# how many play in games were in each year
play_in_info = {
    'bbm': {
        1: range(2001, 2011),
        4: range(2011, analyze.CURRENT_YEAR)
    },
    'bbw': {
        4: range(2022, analyze.CURRENT_YEAR)
    }
}


def write_play_in_results(group: str) -> None:
    """ Determines what happened in the next round for the winners of play-in games. """
    description = analyze.SubgroupDesc(
        group=group,
        title='NCAA Division I',
        suffix="Men's Basketball Tournament",
        tourney='D1',
        directory=f'{group}/D1',
        is_national=True
    )
    # the index is the seed of the favored team, which is not the play-in winner
    winner_counter = pandas.DataFrame(data=0, index=range(1, 9),
                                      columns=['play-in win', 'play-in lose', 'non-play-in win', 'non-play-in lose'])
    for num_games, years in play_in_info[group].items():
        for year in years:
            winner: set[str] = set()
            for game in analyze.get_game(description, year):
                if game[0].seed == game[1].seed > 8:
                    # a play in game (but could be a final four game?)
                    assert len(winner) < num_games
                    winner.add(game[0].team)
                    continue
                if game[0].seed + game[1].seed != 17:
                    # not the first round (but could be a final four game?)
                    continue
                prefix = 'non-' if {g.team for g in game}.isdisjoint(winner) else ''
                win_lose = 'win' if game[0].seed > game[1].seed else 'lose'
                winner_counter.loc[min(game[0].seed, game[1].seed), f'{prefix}play-in {win_lose}'] += 1
    winner_counter.to_csv(f'{group}/D1/playin.csv')


def write_plot_file_round(win_loss_file: str, plot_file: str, should_skip: typing.Callable[[int, int], bool]) -> None:
    """ Create a plot of filtered winning probability confidence intervals (useful for a particular round).
    :param win_loss_file: The numpy csv file to input (probably created by write_plot_file)
    :param plot_file: The tex file to output
    :param should_skip: Function of row and col """
    x_coords: collections.Counter = collections.Counter()
    win_loss = numpy.loadtxt(win_loss_file, dtype=int, delimiter=',')
    win_loss_to_analyze = numpy.zeros((analyze.MAX_SEED + 1, analyze.MAX_SEED + 1), dtype=int)
    with open(plot_file, 'w', encoding='utf-8') as tex_file:
        overall_total = 0
        overall_wins = 0
        for row in range(1, analyze.MAX_SEED+1):
            for col in range(row+1, analyze.MAX_SEED+1):
                if should_skip(row, col):
                    continue
                win_loss_to_analyze[row, col] = win_loss[row, col]
                win_loss_to_analyze[col, row] = win_loss[col, row]
                total = win_loss[row, col] + win_loss[col, row]
                overall_total += total
                overall_wins += win_loss[row, col]
                if total < 10:
                    continue
                center, half_width = analyze.get_confidence_interval(win_loss[row, col], total)
                x_coord = col - row
                print(f'Seeds: {row} v {col}: {center:.2%} +- {half_width:.2%}')
                x_coords[x_coord] += 1
                plotted_x = x_coord + (x_coords[x_coord]-1)/32  # so that identical x_coords don't overlap
                tex_file.write(f'\\draw({plotted_x},{center+half_width})--++(0,{-2*half_width});\n')
        center, half_width = analyze.get_confidence_interval(overall_wins, overall_total)
        print(f'overall: {center:.2%} +- {half_width:.2%}')
    print(analyze.analyze_log_reg(win_loss_to_analyze))


def write_probs_file(winner, filename: str) -> None:
    """ Convert a win/loss matrix into a probability (booktabs TeX) table.
    Used in the presentation (not the paper) because uncertainties are hard to include.
    :param winner: The win/loss numpy matrix
    :param filename: """
    with open(filename, 'w', encoding='utf-8') as tex_file:
        for col in range(1, 17):
            tex_file.write('&{'+str(col)+'}')
        tex_file.write('\\'+'\\'+'\\cmidrule{2-17}'+'\n')
        for row in range(1, 17):
            tex_file.write(f'{row}')
            for col in range(1, 17):
                total = winner[row, col] + winner[col, row]
                tex_file.write('&')
                if total:
                    tex_file.write(f'{winner[row, col] / total:.2}')
            tex_file.write('\\'+'\\'+'\n')
        tex_file.write('\\bottomrule')


def write_simple_plot_file(win_loss_file: str, plot_file: str) -> None:
    """ Create a plot of winning probability confidence intervals.
    :param win_loss_file:
    :param plot_file: """
    win_loss = numpy.loadtxt(win_loss_file, dtype=int, delimiter=',')
    with open(plot_file, 'w', encoding='utf-8') as tex_file:
        for diff in range(1, 16):  # diff = col - row
            wins = 0
            total = 0
            for row in range(1, 17-diff):
                # eg: diff==1: 1<=row<16, 2<=col<17; diff==15: 1<=row<2, 16<=col<17
                wins += win_loss[row, row+diff]
                total += win_loss[row, row+diff] + win_loss[row+diff, row]
            if total < 10:  # == 0:
                continue
            center, half_width = analyze.get_confidence_interval(wins, total)
            tex_file.write(f'\\draw({diff},{center+half_width})--++(0,{-2*half_width});\n')


def write_plots_for_paper() -> None:
    """ Write the plot files used by the paper and presentation. """
    write_plot_file_round('bbm/D1/winloss.csv', 'bbm/D1/winlossRd2.tex', lambda r, c: c - r != 8)
    write_plot_file_round('bbw/D1/winloss.csv', 'bbw/D1/winlossRd2.tex', lambda r, c: c - r != 8)
    write_simple_plot_file('winloss.csv', 'winlosssimpleplot.tex')
    win_loss = numpy.loadtxt('bbm/D1/winloss.csv', dtype=int, delimiter=',')
    write_probs_file(win_loss, 'bbm/D1/winlossprobs.tex')


def print_log_likelihood_round(win_loss_file: str,
                               should_adjust_seeds: bool,
                               should_skip: typing.Callable[[int, int], bool]) -> None:
    """ Analyze how a logistic regression performs in a particular situation (useful for a particular round).
    :param win_loss_file: The numpy csv file to input (probably created by write_plot_file)
    :param should_adjust_seeds:
    :param should_skip: Function of row and col """

    def sigmoid(x: float) -> float:
        return 1/(1+math.exp(-x))

    print(f'avg log likelihood of {win_loss_file}, adjusting seeds: {should_adjust_seeds}')
    win_loss = numpy.loadtxt(win_loss_file, dtype=int, delimiter=',')
    overall_log_reg = analyze.analyze_log_reg(win_loss)
    rate = overall_log_reg['rate']
    total_log_likelihood = 0
    total_games = 0
    for row in range(1, analyze.MAX_SEED + 1):
        for col in range(row + 1, analyze.MAX_SEED + 1):
            if should_skip(row, col):
                continue
            wins = win_loss[row, col]
            losses = win_loss[col, row]
            # if there was one upset, it was by col, of a seed 17-col, for a seed differential of 17-2col
            # and a seed adjustment of .95 + (17-2col)/20 = 1.8 - col/10
            adjust = 1.8 - col/10 if should_adjust_seeds else 0
            log_likelihood = wins*math.log(sigmoid(rate*(col-row-adjust))) \
                + losses*(1-math.log(sigmoid(rate*(row-col+adjust))))
            total_log_likelihood += log_likelihood
            total_games += wins + losses
            if wins + losses < 10:
                continue
            print(f'{row} v {col}: {log_likelihood/(wins+losses)}')
    print(f'overall: {total_log_likelihood/total_games}')


def print_calcs_for_paper() -> None:
    for should_adjust_seeds, group in itertools.product( (False, True), ('bbm', 'bbw') ):
        print_log_likelihood_round(f'{group}/D1/winloss.csv', should_adjust_seeds, lambda r, c: c - r != 8)


def describe_weighted_reseed(reseed_file: str) -> None:
    """ Find the mean and standard deviation of a reseeding column, but weighted by how many games a team has played.
    :param reseed_file: """
    df = pandas.read_csv(reseed_file)
    indexer = (9 < df.Games) & (-16 < df.Reseed) & (df.Reseed < 16) & (0.01 < df.Rate)
    total_games = df[indexer].Games.sum()
    mean = (df[indexer].Games * df[indexer].Reseed).sum() / total_games
    second_moment = (df[indexer].Games * df[indexer].Reseed * df[indexer].Reseed).sum() / total_games
    std = (second_moment - mean*mean)**.5
    print('Teams:', df[indexer].shape[0])
    print('Games:', total_games)
    print('Mean weighted reseeding:', mean)
    print('Std weighted reseeding:', std)


def write_tex_table(group, tourney_group: dict[str, typing.Any]) -> None:
    """ List all the tournaments in a group in one or two booktabs TeX tables.
    I think it might be just as useful to look at the json file, so this isn't used. """
    if 'nonconference' in tourney_group:
        with open(f'paper/table_{group}_natl.tex', 'w', encoding='utf-8') as table:
            for tourney, description in tourney_group.items():
                if tourney.rstrip('_') not in tourney_group['nonconference']:
                    continue
                _write_tex_table_row(table, description.get('title', tourney), description.get('years', None),
                                     description.get('use_suffix', True) and tourney_group['suffix'])
            table.write(r'\bottomrule')
        with open(f'paper/table_{group}_conf.tex', 'w', encoding='utf-8') as table:
            for tourney, description in tourney_group.items():
                if tourney in ('comment', 'suffix', 'nonconference'):
                    continue
                if tourney.rstrip('_') in tourney_group['nonconference']:
                    continue
                _write_tex_table_row(table, description.get('title', tourney), description.get('years', None),
                                     description.get('use_suffix', True) and tourney_group['suffix'])
            table.write(r'\bottomrule')
    else:
        with open(f'paper/table_{group}.tex', 'w', encoding='utf-8') as table:
            for tourney, description in tourney_group.items():
                if tourney in ('comment', 'suffix', 'nonconference'):
                    continue
                _write_tex_table_row(table, description.get('title', tourney), description.get('years', None),
                                     description.get('use_suffix', True)
                                     and group != 'other' and tourney_group['suffix'])
            table.write(r'\bottomrule')


def _write_tex_table_row(table, tourney, years, suffix) -> None:
    """ A single row of a table in write_tex_table """
    table.write(tourney)
    if suffix:
        table.write(' ' + suffix)
    table.write(' & ' + str(years) + ' \\\\\n')


if __name__ == '__main__':
    pass
    # university.check_team_name_starts()

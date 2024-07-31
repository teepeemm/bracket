""" Perform calculations specific to the paper and presentation. """

import collections
import itertools
import json
import math
import re
import typing

import numpy  # type: ignore
import numpy.polynomial  # type: ignore
import pandas  # type: ignore
import scipy.optimize  # type: ignore
import scipy.stats  # type: ignore

import analyze
import university


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


play_in_info = {
    'bbm': {
        1: range(2001, 2011),
        4: range(2011, analyze.CURRENT_YEAR)
    },
    'bbw': {
        4: range(2022, analyze.CURRENT_YEAR)
    }
}
""" how many play in games were in each year """


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
                # x_coord = col - row
                print(f'Seeds: {row} v {col}: {center:.2%} +- {half_width:.2%}')
                x_coords[col - row] += 1
                plotted_x = col - row + (x_coords[col - row]-1)/32  # so that identical x_coords don't overlap
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
    write_play_in_results('bbm')
    write_play_in_results('bbw')
    # for the presentation
    win_loss = numpy.loadtxt('bbm/D1/winloss.csv', dtype=int, delimiter=',')
    write_probs_file(win_loss, 'bbm/D1/winlossprobs.tex')


def print_team_rename_from_stats() -> None:
    """ Print some stats about how teams are renamed throughout this process """
    total_games = 0
    with open('tourneys.json', encoding='utf-8') as json_file:
        tourneys = json.load(json_file)
        for group, tourney_group in tourneys.items():
            if group == 'professional':
                continue
            for tourney, description in tourney_group.items():
                if tourney in ('comment', 'nonconference', 'suffix'):
                    continue
                subgroup_desc = analyze.SubgroupDesc(group=group, directory=f'{group}/{tourney.rstrip("_")}')
                for year in analyze.get_years(description.get('years', None)):
                    for _ in analyze.get_game(subgroup_desc, year):
                        total_games += 1
    university.check_team_name_starts()


def print_prob_one_women_upset() -> None:
    """ The probability that at most one women's D1 team is upset in the first round """
    beta = 0.276

    def p(x):
        return 1/(1+math.exp(-beta*x))

    prob_none = 1
    for s in range(1,9):
        prob_none *= p(2*s-1)**4
    print("probability of no upsets in women's tournament:", prob_none)
    print("probability of at most one upset:", prob_none*(1+4*sum((1/p(17-2*s)-1) for s in range(1,9))))


def print_weighted_reseed(reseed_file: str) -> None:
    """ Find the mean and standard deviation of a reseeding column, but weighted by how many games a team has played.
    :param reseed_file: """
    df = pandas.read_csv(reseed_file)
    print(f'Total teams in {reseed_file}:', df.shape[0])
    indexer = (9 < df.Games) & (-16 != df.Reseed)
    print('10 games, 1 win:', df[indexer].shape[0])
    print('with small beta:', df[indexer & (df.Rate < 0.01)].shape[0])
    indexer = (9 < df.Games) & (-16 < df.Reseed) & (df.Reseed < 16) & (0.01 <= df.Rate)
    total_games = df[indexer].Games.sum()
    mean = (df[indexer].Games * df[indexer].Reseed).sum() / total_games
    second_moment = (df[indexer].Games * df[indexer].Reseed * df[indexer].Reseed).sum() / total_games
    std = (second_moment - mean*mean)**.5
    print('Teams:', df[indexer].shape[0])
    print('Games:', total_games)
    print('Mean weighted reseeding:', mean)
    print('Std weighted reseeding:', std)


def print_prob_several_upsets() -> None:
    """ Determine the probability that a specific sequence of upsets occurred """
    beta = 0.161
    print('naive:', math.prod((sigmoid(beta*s) for s in (-5, 3, -9, -7))))
    print('one upset:', math.prod((sigmoid(beta*s) for s in (-5, 3.88, -8.12, -6.12))))
    print('two upsets:', math.prod((sigmoid(beta*s) for s in (-5, 3.88, -8.12, -5))))


def print_upset_reseed(beta: float, mu0: float, sigma: float) -> None:
    """ Determine the best fit for an upset
    :param beta:
    :param mu0:
    :param sigma: """
    def max_when(x: float, s: float) -> float:
        return beta/(1+math.exp(-beta*(s-x))) - (x-mu0)/sigma**2
    x_vals = [ [1, s] for s in range(1, analyze.MAX_SEED)]
    y_vals = [ scipy.optimize.root_scalar(max_when, (s,), x0=1, x1=2).root for s in range(1, analyze.MAX_SEED)]
    best_fit = scipy.optimize.lsq_linear(x_vals, y_vals).x  # type: ignore
    print(best_fit[0], ' + s /', 1/best_fit[1])


def print_double_upset_reseed(beta: float, mu0: float, sigma: float) -> None:
    """ Determine the best fit for two upsets
    :param beta:
    :param mu0:
    :param sigma: """
    def max_when(x: float, s: tuple[float, float]) -> float:
        return beta/(1+math.exp(-beta*(s[0]-x))) + beta/(1+math.exp(-beta*(s[1]-x))) - (x-mu0)/sigma**2
    x_vals = [ [1, s1, s2] for s1, s2 in itertools.product(range(1, analyze.MAX_SEED), repeat=2) ]
    y_vals = [ scipy.optimize.root_scalar(max_when, (s[1:],), x0=1, x1=2).root for s in x_vals ]
    best_fit = scipy.optimize.lsq_linear(x_vals, y_vals).x  # type: ignore
    print(best_fit[0], ' + s1 /', 1/best_fit[1], ' + s2 /', 1/best_fit[2])


seed_adjust = {
    'bbm/D1/winloss.csv': lambda s: .68+(17-2*s)/25,
    'bbw/D1/winloss.csv': lambda s: .89+(17-2*s)/33
}
""" Copying the output of `print_upset_reseed` """


def print_log_likelihood_round(win_loss_file: str,
                               should_adjust_seeds: bool,
                               should_skip: typing.Callable[[int, int], bool]) -> None:
    """ Analyze how a logistic regression performs in a particular situation (useful for a particular round).
    :param win_loss_file: The numpy csv file to input (probably created by write_plot_file)
    :param should_adjust_seeds:
    :param should_skip: Function of row and col """
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
            adjust = seed_adjust[win_loss_file](col) if should_adjust_seeds else 0
            log_likelihood = wins*math.log(sigmoid(rate*(col-row-adjust))) \
                + losses*(1-math.log(sigmoid(rate*(row-col+adjust))))
            total_log_likelihood += log_likelihood
            total_games += wins + losses
            if wins + losses < 10:
                continue
            print(f'{row} v {col}: {log_likelihood/(wins+losses)}')
    print(f'overall: {total_log_likelihood/total_games}')


def print_calcs_for_paper(page: int = -1) -> None:
    """ :param page: """
    if page in (3, -1):
        print('page 3')
        analyze.analyze_winloss('bbm/D1/winloss.csv')
        analyze.analyze_winloss('bbw/D1/winloss.csv')
        print(scipy.stats.fisher_exact([[76, 852], [225, 1000]], 'less')[1])
        print_prob_one_women_upset()
    if page in (5, -1):
        print('page 5')
        print(scipy.stats.fisher_exact([[9, 9], [40, 30]], 'less')[1])
        print(scipy.stats.fisher_exact([[3, 1], [50, 34]], 'less')[1])
        print(scipy.stats.fisher_exact([[0, 1], [68, 19]], 'less')[1])
        print(scipy.stats.fisher_exact([[1, 0], [78, 19]], 'less')[1])
        print(scipy.stats.fisher_exact([[33, 1], [53, 1]], 'less')[1])
        # overall
        print(scipy.stats.fisher_exact([[46, 12], [289, 103]], 'less')[1])
        # women's
        print(scipy.stats.fisher_exact([[3, 1], [2, 2]], 'less')[1])
        print(scipy.stats.fisher_exact([[4, 0], [4, 0]], 'less')[1])
    if page in (6, -1):
        print('page 6')
        print('disambiguations:',university.TOTAL_DISAMBIGUATIONS)
        print_team_rename_from_stats()
        get_team_performance('bbm', 'D1', 'North Carolina')
        get_team_performance('bbw', 'D1', 'Tennessee')
        print_weighted_reseed('bbm/D1/reseed.csv')
        print_weighted_reseed('bbw/D1/reseed.csv')
    if page in (8, -1):
        print('page 8')
        print_prob_several_upsets()
        print_upset_reseed(0.161, -0.2, 3.2)
        print_double_upset_reseed(0.161, -0.2, 3.2)
        print_upset_reseed(0.276, 0.15, 2.1)
        print_double_upset_reseed(0.276, 0.15, 2.1)
    if page in (9, -1):
        print('page 9')
        for should_adjust_seeds, group in itertools.product( (False, True), ('bbm', 'bbw') ):
            print_log_likelihood_round(f'{group}/D1/winloss.csv', should_adjust_seeds, lambda r, c: c - r != 8)
    if page in (12, -1):
        print('page 12')
        analyze.analyze_winloss('winloss.csv')


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


def sigmoid(x: float) -> float:
    """ :param x: """
    return 1 / (1 + math.exp(-x))


def file_has_unseeded_seeding(filename: str) -> bool:
    """ Does this file have seeding that it shouldn't?  This is a consequence of
    https://en.wikipedia.org/wiki/Module:Team_bracket/doc#Parameters
    "RD_n-seed_m: ... For round 1, this value defaults to the conventional seed allocation for tournaments. "
    :param filename:
    :return: filename has a bracket that should not have seeding but Wikipedia may automatically seed """
    flags = analyze.Flags()
    with open(filename, encoding='utf-8') as fp:
        for bracket, _ in analyze.get_bracket(fp.read(), flags):
            if re.search(r'\d+TeamBracket(?!-NFL)\W', bracket) \
                    and not re.search('TeamBracket-(Compact-)?NoSeeds', bracket) \
                    and not re.search(r'\|\s*seeds\s*=\s*n', bracket) \
                    and not re.search(r'\|\s*RD\d+-seed\d+\s*=', bracket):
                return True
    return False


def find_unseeded_seeding_in(group: str,
                             tourney_group: dict) -> collections.defaultdict[str, list[typing.Optional[int]]]:
    """ :param group:
    :param tourney_group:
    :return: Of all the years in this group, which `file_has_unseeded_seeding()`? """
    unseeded_seeding_years = collections.defaultdict(list)
    for tourney, description_json in tourney_group.items():
        if tourney in ('comment', 'suffix', 'nonconference'):
            continue
        subgroup_desc_vals = analyze.SubgroupDesc(
            group=group,
            directory=f'{group}/{tourney}',
            suffix=tourney_group.get('suffix', ''),
            tourney=tourney,
            is_national='nonconference' not in tourney_group or tourney in tourney_group['nonconference']
        )
        description = subgroup_desc_vals._replace(**description_json)
        for year in analyze.get_years(description.years):
            filename = f'{description.directory.rstrip("_")}/{year}.txt'
            if file_has_unseeded_seeding(filename):
                unseeded_seeding_years[tourney].append(year)
    return unseeded_seeding_years


def write_unseeded_seeding() -> None:
    """ Determine which `file_has_unseeded_seeding()` and write this information to a file.  Also print a summary
    to the console. """
    with open('tourneys.json', encoding='utf-8') as _json_file:
        _tourneys = json.load(_json_file)
    unseeded_seeding = {
        group: find_unseeded_seeding_in(group, tourney_group) for group, tourney_group in _tourneys.items()
    }
    for group, tourneys in unseeded_seeding.items():
        print(group, 'has ', sum((len(years) for years in tourneys.values())))
    with open('unseeded_seeding.json', 'w', encoding='utf-8') as unseeded_file:
        json.dump(unseeded_seeding, unseeded_file, indent=4)


if __name__ == '__main__':
    pass

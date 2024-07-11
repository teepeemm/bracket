""" Functions to analyze tournament seedings.

A key file for __main__ is tourneys.json.  In that file, the highest level is a 'group', consisting of a sport (and
gender in the case of basketball) (although the last group is 'other'). Within a group, each line is another object
corresponding to a tournament with a name and years that tournament occurred. See get_years() for that last item. Often,
a tournament changed their name over the years. In that case, we distinguish the tournaments within the json file by
appending a '_' to the key. This leads to the same directory, and we consolidate the data for the tournament.

This will attempt to locate tournaments through the latest complete year.  This means that as a year progresses,
tournaments that have recently finished will not be evaluated until the end of the calendar year. Note that
FootballFCS and NFL finish their brackets in the following year, so that just after a superbowl is the best time to
get the latest tournaments.

The output csv files that are used by the html GUI are also copied to that directory, with a notable name change:
because I can publish all files in a folder but not a folder itself, files of the form {group}/{tournament}/{file}
are renamed to {group}/{tournament}_{file}. """

from __future__ import annotations
import collections
import datetime
import functools
import glob
import json
import numpy  # type: ignore
import os
import pandas  # type: ignore
import pywikibot  # type: ignore
import re
import time
import typing
import university

from sklearn.linear_model import LogisticRegression  # type: ignore

__author__ = 'Timothy Prescott'
__version__ = '2024-06-12'

numpy.set_printoptions(precision=2, linewidth=106)

CURRENT_YEAR: typing.Final[int] = datetime.date.today().year
MAX_SEED: typing.Final[int] = 20  # 2006 soccer/md2. tennis goes much higher
SECONDS_PER_YEAR: typing.Final[int] = 365*24*60*60

Year = typing.Union[int, list[typing.Union[int, list[int], None]]]
# Description = dict[str,str|Year]


class KeyDefaultDict(collections.defaultdict):
    """ A defaultdict where the default_factory takes the missing key as its argument """
    def __missing__(self, key):
        if self.default_factory is None:
            raise KeyError(key)
        else:
            ret = self[key] = self.default_factory(key)  # type: ignore
            return ret


@functools.singledispatch
def get_years(arg: Year | None) -> typing.Iterator[int] | typing.Iterator[None]:
    """ Returns years of a tournament. """
    raise TypeError('bad year:', type(arg), arg)


@get_years.register
def _get_years_none(_: None) -> typing.Iterator[None]:
    """ The years key wasn't in that description, so there are no years to use """
    yield None


@get_years.register
def _get_years_int(arg: int) -> typing.Iterator[int]:
    """ If get_years took a single int, then it's the starting year and the
    tournament is still ongoing. """
    yield from range(arg, CURRENT_YEAR)  # does not include the current year


class Flags(typing.NamedTuple):
    is_tennis: bool
    is_professional: str | False
    num_teams: int
    multi_elim: bool
    is_national: bool


class SubgroupDesc(typing.NamedTuple):
    group: str = ''
    directory: str = ''
    suffix: str = ''
    tourney: str = ''
    is_national: bool = False
    use_suffix: bool = True
    use_template: bool = False
    title: str = ''
    multi_elim: bool = False
    source_mtime: float = -float('inf')
    years: Year = None
    comment: str = ''


@get_years.register
def _get_years_list(arg: list) -> typing.Iterator[int]:
    """ If get_years took a list, it's a bit more complicated.  A list of two
    ints is a range (but including the endpoints).  Otherwise, an int is a
    single year. And [int,falsy] is a starting year that's still ongoing. """
    if len(arg) == 2 and isinstance(arg[0], int) and isinstance(arg[1], int):
        yield from range(arg[0], arg[1] + 1)
    else:
        for entry in arg:
            if entry is None:
                pass
            elif isinstance(entry, int):
                yield entry
            else:
                assert isinstance(entry, list) and len(entry) == 2
                if entry[1]:
                    yield from range(entry[0], entry[1] + 1)
                else:
                    yield from range(entry[0], CURRENT_YEAR)


class TeamResult:
    """ A team's result of a single game, consisting of their seed and their score """
    def __init__(self, seed: int, team: str, score: int):
        self.seed = seed
        self.team = team.strip()
        self.score = score
        if seed == 0 and re.match(r'\d+\s+\D', team):
            seed_, self.team = re.split(r'\s+', team, maxsplit=1)
            self.seed = int(seed_)

    def __repr__(self):
        return f'Team_Result({self.seed},{self.team},{self.score})'

    def __str__(self):
        return f'({self.seed}) {self.team}: {self.score}'

    @classmethod
    def from_nfl_pieces(cls, seed: str, name: str, score: str, disambiguator: dict[str, str]) -> TeamResult:
        """ Because of how they're formatted, NFL TeamResults can be determined with a single function call """
        seed_ = re.sub(r'\D', '', seed)
        seed_out = int(seed_) if seed_ else 0
        name_out = university.normalize_team_name(name.strip(), disambiguator)
        name_out = university.normalize_professional_name(name_out, 'NFL')
        return cls(seed_out, name_out, int(score))

    @classmethod
    def team_from_series(cls, series_data: dict[str, typing.Any]) -> typing.Iterator[TeamResult]:
        """ Transforms a series of games (eg, best-of-7) into an iterator of individual games
        by copying the team name and seed """
        for score in series_data['scores']:
            yield cls(series_data['seed'], series_data['team'], score)

    @staticmethod
    def dict_has_match_data(team_data: dict[str, typing.Any]) -> bool:
        return team_data.get('team') or team_data.get('seed') or team_data.get('scores')

    @classmethod
    def get_match_data(cls,
                       match_info: list[str],
                       flags: Flags,
                       disambiguator: dict) -> dict[tuple[str, str], dict]:
        """ Take a bracket of information a line at a time and parcel the lines into particular matches """
        match_data: dict[tuple[str, str], typing.Any] = collections.defaultdict(dict)
        for line in match_info:
            matched = re.search(r'RD(\d+)-(team|seed|scores?)(\d+).*=(.*)$', line)
            assert matched is not None
            team_num = (matched.group(1).lstrip('0'), matched.group(3).lstrip('0'))
            item_type = matched.group(2).lower()
            if item_type == 'team':
                if flags.is_tennis:
                    match_data[team_num]['team'] = 'tennis'
                else:
                    match_data[team_num]['team'] = university.normalize_team_name(matched.group(4).strip(),
                                                                                  disambiguator)
                    if flags.is_professional:
                        match_data[team_num]['team'] = \
                            university.normalize_professional_name(match_data[team_num]['team'],
                                                                   flags.is_professional)
            elif item_type == 'seed':
                match_data[team_num]['seed'] = matched.group(4).strip()
            elif 'score' in item_type:
                try:
                    score_in = int(matched.group(4).strip().strip('*† (OT)'))
                except ValueError:
                    score_in = 0
                if 'scores' not in match_data[team_num]:
                    match_data[team_num]['scores'] = []
                match_data[team_num]['scores'].append(score_in)
        return match_data

    @staticmethod
    def fix_seeding(team_num: tuple[str, str], team_data: dict[str, typing.Any], flags: Flags) -> None:
        if 'seed' in team_data and re.search(r'\d', team_data['seed']):
            if re.search(r'\((\d+)\)', team_data['seed']):
                team_data['seed'] = int(re.sub(r'^.*\((\d+)\).*$', r'\1', team_data['seed']))
            elif re.fullmatch(r'\d+-\d+', team_data['seed']):  # tennis sometimes has a range of seeds
                team_data['seed'] = int(re.sub(r'^(\d+)-\d+$', r'\1', team_data['seed']))
            else:
                team_data['seed'] = int(re.sub(r'\D', '', team_data['seed']))
            if MAX_SEED < team_data['seed']:
                team_data['seed'] = MAX_SEED
        elif flags.num_teams != -1 and 'seed' not in team_data and team_num[0] == '1':
            # from https://en.wikipedia.org/wiki/Module:Team_bracket/doc#Parameters
            # "For round 1, this value defaults to the conventional seed allocation for tournaments."
            # It'd be more satisfying to code this, but that'd be longer (and I'm not sure of the algorithm)
            # there also appear to be a few instances where Wikipedia does this but should be told not to:
            # bbm/NCAA/1953, bbm/NIT/1938, baseball/NCAA2/1976
            default_seeding = {
                2: ['', 1, 2],
                3: ['', 2, 3],
                4: ['', 1, 4, 3, 2],
                6: ['', 4, 5, 3, 6, 1, 2],
                8: ['', 1, 8, 4, 5, 2, 7, 3, 6],
                11: ['', 8, 9, 7, 10, 6, 11],
                16: ['', 1, 16, 8, 9, 5, 12, 4, 13, 6, 11, 3, 14, 7, 10, 2, 15]
            }
            if flags.num_teams in default_seeding and int(team_num[1]) < len(default_seeding[flags.num_teams]):
                team_data['seed'] = default_seeding[flags.num_teams][int(team_num[1])]
            else:
                team_data['seed'] = 0
        else:
            team_data['seed'] = 0

    @classmethod
    def game_from_match(cls,
                        match_info: list[str],
                        flags: Flags,
                        disambiguator: dict) -> typing.Generator[Game, None, str]:
        """ Convert the match information into a series of games """
        match_data: dict[tuple[str, str], dict] = cls.get_match_data(match_info, flags, disambiguator)
        for team_num, team_data in match_data.items():
            cls.fix_seeding(team_num, team_data, flags)
        if all('scores' not in team_data for team_data in match_data.values()):
            return 'no scores'
        if any('scores' not in team_data for team_data in match_data.values()):
            return 'missing score'
        if not all(cls.dict_has_match_data(team_data) for team_data in match_data.values()):
            return 'missing data'
        if len({len(team_data['scores']) for team_data in match_data.values()}) != 1:
            # the two team_data['scores'] lists should have the same length
            # put both lengths in a set, and make sure there's only one length in the set
            raise KeyError('differing number of scores')
        if flags.multi_elim \
                and {len(team_data['scores']) for team_data in match_data.values()} == {1} \
                and max(team_data['scores'][0] for team_data in match_data.values()) < 5:
            # multiple elimination, but only one game present. assume the "scores" are really games
            team_data_values: tuple[dict, dict] = tuple(match_data.values())  # type: ignore
            (team_a_data, team_b_data) = team_data_values
            score_a, score_b = team_a_data['scores'][0], team_b_data['scores'][0]
            team_a_data['scores'] = [1] * score_a + [0] * score_b
            team_b_data['scores'] = [0] * score_a + [1] * score_b
        yield from zip(*[cls.team_from_series(series_data) for series_data in match_data.values()])  # type: ignore
        return 'exhausted'  # required by mypy

    def get_conference(self, confs: dict[str, set[str]]):
        for conf, teams in confs.items():
            if self.team in teams:
                return conf
        return 'Unknown'

    def is_empty(self) -> bool:
        """ The team is empty and the score is 0. """
        return self.score == 0 and self.team == ''  # and self.seed == 0


Game = tuple[TeamResult, TeamResult]


def get_bracket(content: str, flags: Flags) -> typing.Iterator[tuple[str, dict]]:
    """ Find brackets within a Wikipedia page
    :param content: The content of the page
    :param flags:
    :returns: The source code of the bracket, with some parsing and simplification already done """
    disambiguator = university.get_disambiguator(content, flags)
    for pattern, repl in disambiguator['replacement'].items():
        content = re.sub(rf'\b{pattern}\b', repl, content)
    for remove in ('&nbsp;', '{{Snd}}', '{{dagger}}', '{{nbsp}}', '{{pen.}}', '{{aet}}', '{{pso}}'):
        content = content.replace(remove, '')
    for remove in ('<ref[^/>]*>.*?</ref>', '<ref [^/>]*/>', "'{2,}", '<!--.*?-->', r'\{\{efn.*?\}\}',
                   '<sup>[^<>]*</sup>', r'<br\s*/?>', r'\{\{#tag:ref[^}]*\}\}', r'\{\{sup[^}]*\}\}',
                   '<small>[^<>]*</small>', r'\{\{small.*?\}\}', r'\{\{flagicon\|[^}]*\}\}', r'[†*^~#]',
                   r'<s>([^<]*)</s>',  # replaced => should delete.  vacated => we'll delete as well
                   r'\{\{s\|[^}]*\}\}'
                   ):
        content = re.sub(remove, '', content, flags=re.MULTILINE | re.DOTALL).strip()
    for extract in (r'\{\{c(?:b|s|f)b [^}]*title=([^}]*)(?=\||\}\})[^}]*\}\}',
                    r'\[\[[^\[\]]*?\|([^\[\]]*?)\]\]',
                    r'\[\[([^\[\]]*?)\]\]',
                    r'\{\{color\|#[0-9A-F]{6}\|([^}]*)\}\}',
                    r'\{\{(?i:CBSB) [^}]*title=([^}]*)(?=\||\}\})[^}]*\}\}',
                    r'\{\{\s*(?i:nowrap|strikethrough)\|([^}]*)\}\}',
                    r'\{\{(?i:csoc link)[^}]*title=([^}]*)(?=\||\}\})[^}]*\}\}',
                    r'\{\{Alternative links\|[^}]*title=([^}]*)(?=\||\}\})[^}]*\}\}'):
        content = re.sub(extract, r'\1', content, flags=re.MULTILINE | re.DOTALL)
    content = content.replace(' & ', ' and ')
    content = re.sub('{{Okina}}', "'", content, flags=re.IGNORECASE)
    for bracket in re.findall(r'\{\{\w+Bracket.*?}}', content, flags=re.MULTILINE | re.DOTALL):
        yield bracket.removeprefix('{{').removesuffix('}}'), disambiguator['suffix']


def get_bracket_info(bracket: str) -> list[list[list[str]]]:
    bracket_info: list[list[list[str]]] = []
    for line in re.split(r'\s*[|\n]\s*', bracket):
        matched = re.match(r'RD(\d+)-(seed|team|score)(\d+)', line)
        # within a round, group(3) identifies the teams: 2n-1 and 2n play each other
        if matched and not re.search('score.*-agg', line):
            round_num = int(matched.group(1))
            match_num = (int(matched.group(3)) + 1) // 2
            while len(bracket_info) <= round_num:
                bracket_info.append([])
            while len(bracket_info[round_num]) <= match_num:
                bracket_info[round_num].append([])
            bracket_info[round_num][match_num].append(line)
    return bracket_info


def get_game_from_nfl_bracket(bracket: str, disambiguator: dict[str, str]) -> typing.Iterator[Game]:
    """ NFL brackets, unlike the others, have an entire game on one line """
    for line in re.split(r'\s*\n\s*', bracket):
        pieces = line.rstrip('|').split('|')
        if len(pieces) < 6:
            continue
        yield (TeamResult.from_nfl_pieces(*pieces[-6:-3], disambiguator),  # type: ignore
               TeamResult.from_nfl_pieces(*pieces[-3:], disambiguator))  # type: ignore


def get_game_from_wikipedia(content: str, flags: Flags) -> typing.Iterator[Game]:
    """ Find the games in the Wikipedia page.
    :param content: The content of the page
    :param flags:
    :returns: Game results
    """
    for bracket, disambiguator in get_bracket(content, flags):
        flags = flags._replace(num_teams=-1)
        num_teams_m = re.match(r'(\d+)TeamBracket\W', bracket)
        if num_teams_m and 'TeamBracket-NoSeeds' not in bracket and not re.search(r'\|\s*seeds\s*=\s*n', bracket):
            flags = flags._replace(num_teams=int(num_teams_m.group(1)))
        if 'TeamBracket-NFL' in bracket:
            yield from get_game_from_nfl_bracket(bracket, disambiguator)
        else:
            bracket_info = get_bracket_info(bracket)
            for round_info in bracket_info:
                for match_info in round_info:
                    yield from TeamResult.game_from_match(match_info, flags, disambiguator)


def get_game(description: SubgroupDesc, year: int | None) -> typing.Iterator[Game]:
    """ Get games from Wikipedia according to a description.
    :param description: Necessary details to locate the Wikipedia page.  Needs at least keys 'directory' & 'group'.
    :param year: """
    filename = f'{description.directory.rstrip("_")}/{year}.txt'
    if not os.path.isfile(filename) or os.path.getmtime(filename) + SECONDS_PER_YEAR < time.time():
        potential_titles = get_potential_titles(description, year, description.tourney == 'NFL_')
        if not create_wiki_cache(filename, potential_titles):
            return
    flags = Flags(
        multi_elim=description.multi_elim,
        is_tennis=description.directory == 'other/Tennis',
        is_professional=description.group == 'professional' and description.tourney,
        is_national=description.is_national,
        num_teams=-1
    )
    with open(filename) as fp:
        for game in get_game_from_wikipedia(fp.read(), flags):
            if game[0].score < game[1].score:
                game = game[1], game[0]
            yield game


def get_source_mtime(directory: str, years: typing.Iterator[int] | typing.Iterator[None]) -> float:
    """ The most recent modification time of the source wiki files in this directory
    :param directory:
    :param years: The years to examine in this directory
    :return: The most recent modification time, or +inf """
    try:
        return max(os.path.getmtime(f'{directory.rstrip("_")}/{year}.txt') for year in years)
    except FileNotFoundError:
        return float('inf')


def get_potential_titles(description: SubgroupDesc, year: int | None, use_range: bool) -> list[str]:
    """ Determines potential titles that Wikipedia may use for a tournament.
    Sometimes the suffix is .lower()ed, and some tournaments have a template.
    NFL playoffs use YYYY-(YY)YY (see _get_year_range), and sometimes that dash is an en-dash.
    :param description: the dict describing the details of this tournament
    :param year: The year of the tournament
    :param use_range: Whether to use _get_year_range for the year """
    tourney_title = description.title or description.tourney.upper()
    potential_title = tourney_title
    if year:
        if use_range:
            potential_title = f'{_get_year_range(year)} ' + potential_title
        else:
            potential_title = f'{year} ' + potential_title
    potential_titles = []
    if description.use_template:
        potential_titles.append('Template:' + potential_title)
    if description.use_suffix and description.group != 'other':
        potential_titles.append(potential_title + ' ' + description.suffix)
        potential_titles.append(potential_title + ' ' + description.suffix.lower())
    else:
        potential_titles.append(potential_title)
    if use_range:
        en_dash_years = [potential.replace('-', '\u2013') for potential in potential_titles]
        potential_titles.extend(en_dash_years)
    return potential_titles


def _get_year_range(year_in: int) -> str:
    """ Convert a single year into a range of that year and the next.  This is the format for the NFL playoffs. """
    if year_in == 1999:
        return '1999–2000'
    return f'{year_in}–{(year_in+1)%100:02}'


def create_wiki_cache(filename: str, potential_titles: list[str]) -> bool:
    """ Gets the site's contents from Wikipedia and caches them to a file.
    (Tail) recursively checks each potential title, and uses the first that works.
    :param filename: The cache file to use
    :param potential_titles: The potential sites in Wikipedia.
    :returns: Whether the site was found """
    if not potential_titles:
        print(filename, 'does not exist')
        return False
    potential_title = potential_titles.pop(0)
    site = pywikibot.Site('en', 'wikipedia')
    page = None
    try:
        page = pywikibot.Page(site, potential_title)
        content = page.get()
        print('writing', filename, 'from', potential_title)
        with open(filename, 'w') as fp:
            fp.write(content)
        return True
    except pywikibot.exceptions.NoPageError:
        pass
    except ConnectionError:
        print('offline. could not write', filename)
        return False
    except pywikibot.exceptions.IsRedirectPageError:
        assert page is not None
        redirect = page.get(get_redirect=True)
        # get the content of the first [[link]]
        redirect_title = re.sub(r'^[^\[]*\[\[([^]]*)]].*$', r'\1', redirect, flags=re.DOTALL | re.MULTILINE)
        potential_titles.insert(0, redirect_title)
    return create_wiki_cache(filename, potential_titles)


def write_plot_file(winner, filename: str) -> None:
    """ Create a plot of winning probability confidence intervals.
    :param winner: The win/loss numpy matrix
    :param filename: """
    x_coords: collections.Counter = collections.Counter()
    with open(filename, 'w') as tex_file:
        for row in range(1, 16):
            for col in range(row+1, 17):
                total = winner[row, col] + winner[col, row]
                if total < 10:  # == 0:
                    continue
                center, half_width = get_confidence_interval(winner[row, col], total)
                x_coord = col - row
                x_coords[x_coord] += 1
                plotted_x = x_coord + (x_coords[x_coord]-1)/32  # so that identical x_coords don't overlap
                tex_file.write(f'\\draw({plotted_x},{center+half_width})--++(0,{-2*half_width});\n')


def write_simple_plot_file(win_loss_file: str, plot_file: str) -> None:
    """ Create a plot of winning probability confidence intervals.
    :param win_loss_file:
    :param plot_file: """
    win_loss = numpy.loadtxt(win_loss_file, dtype=int, delimiter=',')
    with open(plot_file, 'w') as tex_file:
        for diff in range(1, 16):  # diff = col - row
            wins = 0
            total = 0
            for row in range(1, 17-diff):
                # eg: diff==1: 1<=row<16, 2<=col<17; diff==15: 1<=row<2, 16<=col<17
                wins += win_loss[row, row+diff]
                total += win_loss[row, row+diff] + win_loss[row+diff, row]
            if total < 10:  # == 0:
                continue
            center, half_width = get_confidence_interval(wins, total)
            tex_file.write(f'\\draw({diff},{center+half_width})--++(0,{-2*half_width});\n')


def write_plot_file_round(win_loss_file: str, plot_file: str, should_skip: typing.Callable[[int, int], bool]) -> None:
    """ Create a plot of filtered winning probability confidence intervals (useful for a particular round).
    :param win_loss_file: The numpy csv file to input (probably created by write_plot_file)
    :param plot_file: The tex file to output
    :param should_skip: Function of row and col """
    x_coords: collections.Counter = collections.Counter()
    win_loss = numpy.loadtxt(win_loss_file, dtype=int, delimiter=',')
    win_loss_to_analyze = numpy.zeros((MAX_SEED + 1, MAX_SEED + 1), dtype=int)
    with open(plot_file, 'w') as tex_file:
        overall_total = 0
        overall_wins = 0
        for row in range(1, 16):
            for col in range(row+1, 17):
                if should_skip(row, col):
                    continue
                win_loss_to_analyze[row, col] = win_loss[row, col]
                win_loss_to_analyze[col, row] = win_loss[col, row]
                total = win_loss[row, col] + win_loss[col, row]
                overall_total += total
                overall_wins += win_loss[row, col]
                if total < 10:
                    continue
                center, half_width = get_confidence_interval(win_loss[row, col], total)
                x_coord = col - row
                print(f'Seeds: {row} v {col}: {center:.2%} +- {half_width:.2%}')
                x_coords[x_coord] += 1
                plotted_x = x_coord + (x_coords[x_coord]-1)/32  # so that identical x_coords don't overlap
                tex_file.write(f'\\draw({plotted_x},{center+half_width})--++(0,{-2*half_width});\n')
            center, half_width = get_confidence_interval(overall_wins, overall_total)
        print(f'overall: {center:.2%} +- {half_width:.2%}')
    print(analyze_log_reg(win_loss_to_analyze))


def write_win_loss(group: str | None, directories: typing.Iterable[str]) -> None:
    """ Collect several win_loss files into one.
    :param group: The destination (or current) directory
    :param directories: The location of the winloss files to collect """
    win_loss_file = 'winloss.csv'
    prefix = (group + '/') if group else ''
    win_loss_file = prefix + win_loss_file
    source_mtime = max(os.path.getmtime(prefix + directory + '/winloss.csv') for directory in directories)
    try:
        if source_mtime < os.path.getmtime(win_loss_file):
            return
    except FileNotFoundError:
        pass
    winner = numpy.zeros((MAX_SEED + 1, MAX_SEED + 1), dtype=int)
    for directory in directories:
        winner += numpy.loadtxt(prefix + directory + '/winloss.csv', dtype=int, delimiter=',')
    numpy.savetxt(win_loss_file, winner, delimiter=',', fmt='%d')  # type: ignore
    numpy.savetxt('html/'+win_loss_file, winner, delimiter=',', fmt='%d')  # type: ignore
    write_plot_file(winner, win_loss_file.replace('loss.csv', 'lossplot.tex'))


def write_reseeding_approx(group: str | None, directories: typing.Iterable[str]) -> None:
    """ Collect several reseeding files into one (linear) approximation.
    :param group: The destination (or current) directory
    :param directories: The location of the reseed files to collect """
    reseed_file = 'reseed_approx.csv'
    prefix = (group + '/') if group else ''
    reseed_file = prefix + reseed_file
    directory_list = [prefix + g for g in directories if g != 'professional']
    if group:
        source_mtime = max(os.path.getmtime(directory + '/reseed.csv') for directory in directory_list)
    else:
        source_mtime = max(os.path.getmtime(directory + '/reseed_approx.csv') for directory in directory_list)
    try:
        if source_mtime < os.path.getmtime(reseed_file):
            return
    except FileNotFoundError:
        pass
    if group:
        reseed_files = [pandas.read_csv(directory + '/reseed.csv') for directory in directory_list]
    else:
        reseed_files = [pandas.read_csv(directory + '/reseed_approx.csv') for directory in directory_list]
    combined = pandas.concat(reseed_files)
    combined['GamesRate'] = combined['Games']*combined['Rate']
    combined['GamesReseed'] = combined['Games']*combined['Reseed']
    grouped = combined.groupby('Team').sum()
    grouped['One'] = 1
    grouped['Games'] = grouped[['Games', 'One']].max(axis='columns')
    grouped['Rate'] = grouped['GamesRate'] / grouped['Games']
    grouped['Reseed'] = grouped['GamesReseed'] / grouped['Games']
    grouped.to_csv(reseed_file, columns=['Games', 'Rate', 'Reseed'])
    grouped.to_csv('html/'+reseed_file, columns=['Games', 'Rate', 'Reseed'])


def write_states(group: str | None, directories: typing.Iterable[str]) -> None:
    """ Collect several states files into one.  The eventual state.csv is a good place to look to see which universities
    are in which states, and if any corrections need to be made.
    :param group: The destination (or current) directory
    :param directories: The location of the states files to collect """
    state_file = 'state.csv'
    prefix = (group + '/') if group else ''
    state_file = prefix + state_file
    directory_list = [prefix + g for g in directories if g != 'professional']
    source_mtime = max(os.path.getmtime(directory + '/state.csv') for directory in directory_list)
    try:
        if source_mtime < os.path.getmtime(state_file):
            return
    except FileNotFoundError:
        pass
    state_files: list[pandas.DataFrame] = [pandas.read_csv(directory + '/state.csv') for directory in directory_list]
    combined = pandas.concat(state_files)
    output = combined.fillna('').groupby(['Team', 'State']).sum().sort_values(['State', 'Total', 'Team'])
    output.to_csv(state_file)
    if not group or group == 'professional':
        output.to_csv('html/'+state_file)
    # combined.fillna('').groupby(['Team', 'State']).sum().sort_values(['Team', 'State']).to_csv(state_file)


def write_group_betas(group: str, nonconference: list[str]) -> None:
    """ The upset rate *within* a conference """
    group_beta: list[dict[str, str | float]] = []
    output = group+'/group_betas.csv'
    win_loss_files = list(glob.glob(f'{group}/*/winloss.csv'))
    source_mtime = max((os.path.getmtime(f) for f in win_loss_files))
    try:
        if source_mtime < os.path.getmtime(output):
            return
    except FileNotFoundError:
        pass
    for win_loss_file in win_loss_files:
        conference = win_loss_file.removeprefix(group+'/').removesuffix('/winloss.csv')
        win_loss = numpy.loadtxt(win_loss_file, dtype=int, delimiter=',')
        analysis = analyze_log_reg(win_loss)
        beta = -analysis['rate']
        games = analysis['games']
        if 0 < beta:
            group_beta.append({
                'Conference': conference,
                'Games': games,
                'Rate': beta,
                'IsNational': int(conference in nonconference)
            })
    df = pandas.DataFrame(group_beta)
    out_df = df.sort_values('Rate', ascending=False)
    out_df.to_csv(output, index=False)
    out_df.to_csv('html/'+output, index=False)


def get_team_performance(group: str, tourney: str, team: str) -> None:
    """ Summarize how a team has performed within a specific tournament. """
    with open('tourneys.json') as json_file:
        tourneys = json.load(json_file)
    description = SubgroupDesc(**tourneys[group][tourney])._replace(
        group=group, tourney=tourney, directory=f'{group}/{tourney}',
        suffix=tourneys[group].get('suffix', None),
        is_national=tourney in tourneys[group].get('nonconference', (tourney,)))
    win_loss_seeds: dict[str, collections.Counter] = {
        'wins': collections.Counter(),
        'losses': collections.Counter()
    }
    for year in get_years(description.years):
        for game in get_game(description, year):
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
    print(calc_log_reg(win_loss_seeds_with_list))


play_in_info = {
    'bbm': {
        1: range(2001, 2011),
        4: range(2011, CURRENT_YEAR)
    },
    'bbw': {
        4: range(2022, CURRENT_YEAR)
    }
}


def write_play_in_results(group: str) -> None:
    """ Determines what happened in the next round for the winners of play-in games. """
    description = SubgroupDesc(
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
            for game in get_game(description, year):
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


def identity(entered: str, **_) -> str:
    """ Returns its argument
    :param entered: The argument to return
    :param _: Not used. Only present to allow write_overall_reseeding to take 'group' as a keyword """
    return entered


def write_overall_reseeding(tourneys: dict[str, typing.Any],
                            grouper: typing.Callable[[str, str], str] = identity,
                            label: str = '') -> None:
    try:
        source_mtime = max((get_source_mtime(f'{group}/{tourney.rstrip("_")}',
                                             get_years(description.get('years', None)))
                            for group, tourney_group in tourneys.items()
                            for tourney, description in tourney_group.items()
                            if tourney not in ('suffix', 'comment', 'nonconference')))
        # description should be a SubgroupDesc in the previous command, but since we only need the years entry,
        # we stick with a dict
        if source_mtime < os.path.getmtime(f'{label}reseed.csv'):
            return
    except FileNotFoundError:
        pass
    outcomes: collections.defaultdict[str, dict[str, list[int]]] = collections.defaultdict(
        lambda: {'wins': [], 'losses': []})
    for group, tourney_group in tourneys.items():
        if group == 'professional':
            continue
        for tourney, description_dict in tourney_group.items():
            if tourney in ('suffix', 'comment', 'nonconference'):
                continue
            description = SubgroupDesc(**description_dict)._replace(
                group=group, tourney=tourney, directory=f'{group}/{tourney.rstrip("_")}',
                is_national=tourney in tourney_group.get('nonconference', (tourney,)),
                suffix=tourney_group.get('suffix', ''))
            _update_reseeding(outcomes, description, functools.partial(grouper, group=group))
    reseeding: list[dict[str, str | int]] = [calc_log_reg(v) | {'Team': k} for k, v in outcomes.items()] or \
        [{'Team': 'NA', 'Games': 0, 'Rate': 0, 'Reseed': 0}]
    df = pandas.DataFrame(reseeding)
    output = df.sort_values('Team')
    columns = ['Team', 'Games', 'Rate', 'Reseed']
    output.to_csv(f'{label}reseed.csv', index=False, columns=columns)
    output.to_csv(f'html/{label}reseed.csv', index=False, columns=columns)
    if not label:
        indexer = (9 < df.Games) & (-10 < df.Reseed) & (df.Reseed < 10)
        output = df[indexer].sort_values('Team')
        output.to_csv(f'reseed_filtered.csv', index=False, columns=columns)
        output.to_csv(f'html/reseed_filtered.csv', index=False, columns=columns)


def write_group_reseeding(group: str,
                          tourney_group: dict[str, typing.Any],
                          grouper: typing.Callable[[str], str] = identity,
                          label: str = '') -> None:
    """ Creates the files {group}/{label}reseed[_filtered].csv.
    pgf/simplecsv is not up to handling the larger csvs.
    :param group:
    :param tourney_group:
    :param grouper: Collects various teams into grouper(team).  Passed to _update_reseeding
    :param label: """
    try:
        source_mtime = max((get_source_mtime(f'{group}/{tourney.rstrip("_")}',
                                             get_years(description.get('years', None)))
                            for tourney, description in tourney_group.items()
                            if tourney not in ('suffix', 'comment', 'nonconference')))
        # again, description should be a SubgroupDesc
        if source_mtime < os.path.getmtime(f'{group}/{label}reseed.csv'):
            return
    except FileNotFoundError:
        pass
    outcomes: collections.defaultdict[str, dict[str, list[int]]] = collections.defaultdict(
        lambda: {'wins': [], 'losses': []})
    for tourney, description_dict in tourney_group.items():
        if tourney in ('suffix', 'comment', 'nonconference'):
            continue
        description = SubgroupDesc(**description_dict)._replace(
            group=group, tourney=tourney, directory=f'{group}/{tourney.rstrip("_")}',
            is_national=tourney in tourney_group.get('nonconference', (tourney,)),
            suffix=tourney_group.get('suffix', ''))
        _update_reseeding(outcomes, description, grouper)
    reseeding: list[dict[str, str | int]] = [calc_log_reg(v) | {'Team': k} for k, v in outcomes.items()] or \
        [{'Team': 'NA', 'Games': 0, 'Rate': 0, 'Reseed': 0}]
    df = pandas.DataFrame(reseeding)
    output = df.sort_values('Team')
    columns = ['Team', 'Games', 'Rate', 'Reseed']
    output.to_csv(f'{group}/{label}reseed.csv', index=False, columns=columns)
    output.to_csv(f'html/{group}/{label}reseed.csv', index=False, columns=columns)
    if not label:
        indexer = (9 < df.Games) & (-10 < df.Reseed) & (df.Reseed < 10)
        output = df[indexer].sort_values('Team')
        output.to_csv(f'{group}/reseed_filtered.csv', index=False, columns=columns)
        output.to_csv(f'html/{group}/reseed_filtered.csv', index=False, columns=columns)


def _update_reseeding(outcomes: collections.defaultdict[str, dict[str, list[int]]],
                      description: SubgroupDesc,
                      grouper: typing.Callable[[str], str]) -> None:
    for year in get_years(description.years):
        for game in get_game(description, year):
            if any((g.is_empty() for g in game)) or game[0].seed == game[1].seed == 0:
                continue
            seed_diff = game[0].seed - game[1].seed  # positive value is an upset
            outcomes[grouper(game[0].team)]['wins'].append(-seed_diff)
            outcomes[grouper(game[1].team)]['losses'].append(seed_diff)


def analyze_tourney_subgroup(group: str,
                             tourney: str,
                             tourney_subgroup: dict[str, typing.Any],
                             suffix: str,
                             is_national: bool) -> None:
    """
    :param group: The group containing this tournament.
    :param tourney: This tournament.
    :param tourney_subgroup: The sub-dictionary of tourney_group that holds the variations
    :param suffix: Taken from the tourney group
    :param is_national: That the tournament has a national (non-conference) scope """
    directory = f'{group}/{tourney}'
    if os.path.isdir(directory):
        source_mtime = max((get_source_mtime(directory, get_years(description.get('years', None)))
                            for description in tourney_subgroup.values()))
    else:
        os.mkdir(directory)
        source_mtime = float('inf')
    subgroup_desc = SubgroupDesc(
        group=group,
        directory=directory,
        suffix=suffix,
        tourney=tourney,
        source_mtime=source_mtime,
        is_national=is_national
    )
    write_tourney_win_loss(subgroup_desc, tourney_subgroup)
    write_tourney_reseeding(subgroup_desc, tourney_subgroup)
    write_tourney_reseeding(subgroup_desc, tourney_subgroup,
                            functools.partial(university.get_state, group=group), 'state_')
    write_tourney_reseeding(subgroup_desc, tourney_subgroup,
                            functools.partial(university.get_timezone, group=group), 'tz_')
    write_tourney_states(subgroup_desc, tourney_subgroup)


def write_tourney_reseeding(subgroup_desc: SubgroupDesc,
                            tourney_subgroup: dict[str, typing.Any],
                            grouper: typing.Callable[[str], str] = identity,
                            label: str = '') -> None:
    """ Determine how teams have performed in a tournament.
    :param subgroup_desc:
    :param tourney_subgroup:
    :param grouper: Collects various teams into grouper(team).  Passed to _update_reseeding
    :param label: """
    reseeding_file: str = subgroup_desc.directory + f'/{label}reseed.csv'
    try:
        if subgroup_desc.source_mtime < os.path.getmtime(reseeding_file):
            return
    except FileNotFoundError:
        pass
    outcomes: collections.defaultdict[str, dict[str, list[int]]] = collections.defaultdict(
        lambda: {'wins': [], 'losses': []})
    for tourney, description in tourney_subgroup.items():
        description.update(subgroup_desc)
        _update_reseeding(outcomes, description, grouper)
    reseeding = [calc_log_reg(v) | {'Team': k} for k, v in outcomes.items()] or \
        [{'Team': 'NA', 'Games': 0, 'Rate': 0, 'Reseed': 0}]
    output = pandas.DataFrame(reseeding).sort_values(['Team', 'Games'])
    columns = ['Team', 'Games', 'Rate', 'Reseed']
    output.to_csv(reseeding_file, index=False, columns=columns)
    output.to_csv('html/'+'_'.join(reseeding_file.rsplit('/', 1)), index=False, columns=columns)


def write_tourney_states(subgroup_desc: SubgroupDesc, tourney_subgroup: dict[str, typing.Any]) -> None:
    """ List all the teams and their states that have participated in a tournament. """

    def default_key(group: str, key: str) -> collections.abc.Sequence[str | int]:
        return [university.get_state(key, group)] + [0] * 5

    state_file: str = subgroup_desc.directory + '/state.csv'
    try:
        if subgroup_desc.source_mtime < os.path.getmtime(state_file):
            return
    except FileNotFoundError:
        pass
    states: collections.defaultdict[str, list[str | int]] = \
        KeyDefaultDict(functools.partial(default_key, subgroup_desc.group))
    for tourney, description in tourney_subgroup.items():
        description.update(subgroup_desc)
        for year in get_years(description.get('years', None)):
            for game in get_game(subgroup_desc, year):
                if game[0].seed and game[1].seed:
                    indices = 2, 2
                elif game[0].seed:
                    indices = 3, 2
                elif game[1].seed:
                    indices = 4, 3
                else:
                    indices = 5, 5
                for index, indice in enumerate(indices):
                    states[game[index].team][1] += 1
                    states[game[index].team][indice] += 1
    columns = ['State', 'Total', 'Both seeded', 'Seeded', 'Opp seeded', 'Not seeded']
    towrite = pandas.DataFrame(data=states.values(), columns=columns, index=states.keys()).rename_axis(index='Team')
    output = towrite.sort_index(axis='index')
    output.to_csv(state_file)


def write_tourney_win_loss(subgroup_desc: SubgroupDesc, tourney_subgroup: dict[str, typing.Any]) -> None:
    """ This creates a 2d array where (row,col) is the number of times row beat col and writes this
    to a csv in the tournament directory. """
    win_loss_file: str = subgroup_desc.directory + '/winloss.csv'
    try:
        if subgroup_desc.source_mtime < os.path.getmtime(win_loss_file):
            return
    except FileNotFoundError:
        pass
    tourney_winner = numpy.zeros((MAX_SEED + 1, MAX_SEED + 1), dtype=int)
    for tourney, description_dict in tourney_subgroup.items():
        description = SubgroupDesc(**description_dict)._replace(**subgroup_desc._asdict())
        for year in get_years(description.years):
            for game in get_game(description, year):
                tourney_winner[game[0].seed, game[1].seed] += 1
    numpy.savetxt(win_loss_file, tourney_winner, delimiter=',', fmt='%d')  # type: ignore
    numpy.savetxt('html/'+'_'.join(win_loss_file.rsplit('/', 1)),
                  tourney_winner, delimiter=',', fmt='%d')  # type: ignore
    write_plot_file(tourney_winner, win_loss_file.replace('loss.csv', 'lossplot.tex'))


def analyze_confs(group: str, tourney_group: dict[str, typing.Any]) -> None:
    reseeding_file = group + '/conf_reseed.csv'
    try:
        if os.path.getmtime(group+'/reseed_approx.csv') <= os.path.getmtime(reseeding_file):
            return
    except FileNotFoundError:
        pass
    all_years: dict[int | None, list[str]] = collections.defaultdict(list)
    outcomes: collections.defaultdict[str, dict[str, list[int]]] = collections.defaultdict(
        lambda: {'wins': [], 'losses': []})
    # start by finding which years have a tournament we should look at
    for tourney, description in tourney_group.items():
        if tourney in ('suffix', 'nonconference', 'comment'):
            continue
        for year in get_years(description.get('years', None)):  # NFL does not get to analyze_confs
            all_years[year].append(tourney)
    all_years.pop(None, None)
    for year, tourneys in all_years.items():
        # Conferences change over the years. Any tournament determines that conference's teams for that year
        confs: dict[str, set[str]] = collections.defaultdict(set)
        for tourney in tourneys:
            if tourney.rstrip('_') in tourney_group['nonconference']:
                continue
            tourney_group[tourney].update(group=group, directory=f'{group}/{tourney}'.rstrip('_'), is_national=False)
            confs[tourney.rstrip('_')] |= {t.team for game in get_game(tourney_group[tourney], year) for t in game}
        # now look through the nonconference tournaments
        for tourney, description_dict in tourney_group.items():
            description = SubgroupDesc(**description_dict)._replace(
                group=group, directory=f'{group}/{tourney}'.rstrip('_'), is_national=True)
            if tourney.rstrip('_') not in tourney_group['nonconference']:
                continue
            if year not in get_years(description.years):  # NFL does not get to analyze_confs
                continue
            for game in get_game(description, year):
                if not (game[0].seed and game[1].seed):
                    continue
                # find the inter-conference games
                conf = [g.get_conference(confs) for g in game]
                if conf[0] == conf[1]:
                    continue
                seed_diff = game[0].seed - game[1].seed  # positive value is an upset
                outcomes[conf[0]]['wins'].append(-seed_diff)
                outcomes[conf[1]]['losses'].append(seed_diff)
    reseeding: list[dict[str, str | float]] = [calc_log_reg(v) | {'Conference': k} for k, v in outcomes.items()] or \
        [{'Conference': 'Unknown', 'Games': 0, 'Rate': 0, 'Reseed': 0}]
    df = pandas.DataFrame(reseeding)
    df['ConferenceIsKnown'] = (df['Conference'] != 'Unknown').astype(int)
    output = df.sort_values(['Conference', 'Games'])
    columns = ['Conference', 'Games', 'Rate', 'Reseed', 'ConferenceIsKnown']
    output.to_csv(reseeding_file, index=False, columns=columns)
    output.to_csv('html/'+reseeding_file, index=False, columns=columns)


def analyze_tourney_group(group: str, tourney_group: dict[str, typing.Any]) -> None:
    """
    :param group: The key within the json file, identifying the group
    :param tourney_group: The value, listing the various tournaments of that group """
    directories = [k for k in tourney_group.keys()
                   if k not in ('comment', 'suffix', 'nonconference') and not k.endswith('_')]
    for tourney in directories:
        tourney_subgroup = {k: v for k, v in tourney_group.items() if k.rstrip('_') == tourney}
        analyze_tourney_subgroup(group, tourney, tourney_subgroup, tourney_group.get('suffix', ''),
                                 'nonconference' not in tourney_group or tourney in tourney_group['nonconference'])
    write_win_loss(group, directories)
    write_reseeding_approx(group, directories)
    write_states(group, directories)
    write_group_betas(group, tourney_group.get('nonconference', []))
    analyze_winloss(group + '/winloss.csv')
    write_group_reseeding(group, tourney_group)
    write_group_reseeding(group, tourney_group, functools.partial(university.get_state, group=group), 'state_')
    write_group_reseeding(group, tourney_group, functools.partial(university.get_timezone, group=group), 'tz_')
    if group not in ('other', 'professional'):
        analyze_confs(group, tourney_group)


def analyze_overall(tourneys: dict[str, typing.Any]) -> None:
    """ Analyze the json object.  This is the main function of the module.
    :param tourneys: The json object to analyze. """
    for group, tourney_group in tourneys.items():
        if not os.path.isdir(group):
            os.mkdir(group)
        analyze_tourney_group(group, tourney_group)
    write_win_loss(None, tourneys.keys())
    write_reseeding_approx(None, tourneys.keys())
    write_states(None, tourneys.keys())
    write_overall_reseeding(tourneys)
    write_overall_reseeding(tourneys, university.get_state, 'state_')
    write_overall_reseeding(tourneys, university.get_timezone, 'tz_')
    analyze_winloss('winloss.csv', True)


def analyze_log_reg(winner: numpy.ndarray) -> dict[str, float]:
    """ Perform a logistic regression on a winloss matrix
    :param winner: The winloss matrix
    :returns: The analysis, with keys 'games', 'rate', and 'loss per game' """
    diff = [winner[1:, 1:].trace(-i) for i in range(1 - MAX_SEED, MAX_SEED)]
    if not sum(diff):
        return {
            'games': 0,
            'rate': 0,
            'loss per game': 0
        }
    diff_rev = [*reversed(diff)]
    x, y = [], []
    for n, (wins, losses) in enumerate(zip(diff, diff_rev), start=1 - MAX_SEED):
        x.extend([n] * (wins + losses))
        y.extend([1] * wins + [0] * losses)
    xx = numpy.array(x).reshape(-1, 1)
    clf = LogisticRegression(fit_intercept=False).fit(xx, y)  # force the intercept to be 0 because of symmetry
    prob_matrix = clf.predict_proba(numpy.array(range(1 - MAX_SEED, MAX_SEED)).reshape(-1, 1))
    losswin = numpy.column_stack((diff_rev, diff))
    total_loss = -(numpy.log(prob_matrix) * losswin).sum(axis=(0, 1))
    return {
        'games': sum(diff),
        'rate': clf.coef_[0, 0],
        'loss per game': total_loss / sum(diff)
    }


def analyze_winloss(filename: str, show_grids=False) -> None:
    """ Analyze a winloss matrix file
    :param filename: The file in question
    :param show_grids: Whether to print the (probability) matrix along with the analysis """
    winner = numpy.loadtxt(filename, dtype=int, delimiter=',')
    print(filename, analyze_log_reg(winner))
    print(winner.sum(axis=(0, 1)), 'total games. ', winner[1:, 1:].sum(axis=(0, 1)), 'games between ranked teams')
    if show_grids:
        print(winner[1:, 1:])
        winner_loser = numpy.ma.MaskedArray(winner + winner.T, copy=True, mask=(winner + winner.T) < 6)
        probs = winner / winner_loser
        print(probs[1:, 1:].filled(numpy.nan))


def calc_log_reg(win_loss_seeds: dict[str, list[int]]) -> dict[str, float]:
    """ Compute the logistic regression in the form 1/(1+exp(-rate(x-reseed))).
    :param win_loss_seeds: A dictionary with keys 'wins' and 'losses' and values the corresponding lists
    :returns: A dictionary with keys 'Games', 'Rate', and 'Reseed' """
    x = win_loss_seeds['wins'] + win_loss_seeds['losses']
    y = [1] * len(win_loss_seeds['wins']) + [0] * len(win_loss_seeds['losses'])
    if len(set(y)) == 1:
        return {
            'Games': len(x),
            'Rate': 0,
            'Reseed': 16 if win_loss_seeds['losses'] else -16
        }
    xx = numpy.array(x).reshape(-1, 1)
    clf = LogisticRegression().fit(xx, y)
    return {
        'Games': len(x),
        'Rate': clf.coef_[0, 0],
        'Reseed': clf.intercept_[0] / clf.coef_[0, 0] if clf.coef_[0, 0] else 0
    }


def get_confidence_interval(successes: int, total: int) -> tuple[float, float]:
    """ Determine a Wilson confidence interval, see Brown reference """
    kappa = 1.96  # standard deviations to get 95% confidence
    kappa_sq = kappa*kappa
    phat = successes / total
    qhat = (total - successes) / total
    center = (successes + kappa_sq / 2) / (total + kappa_sq)
    half_width = kappa * total ** .5 * (phat * qhat + kappa_sq / (4 * total)) ** .5 / (total + kappa_sq)
    return center, half_width


def write_probs_file(winner, filename: str) -> None:
    """ Convert a win/loss matrix into a probability (booktabs TeX) table.
    Used in the presentation (not the paper) because uncertainties are hard to include.
    :param winner: The win/loss numpy matrix
    :param filename: """
    with open(filename, 'w') as tex_file:
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


def write_tex_table(group, tourney_group: dict[str, typing.Any]) -> None:
    """ List all the tournaments in a group in one or two booktabs TeX tables.
    I think it might be just as useful to look at the json file, so this isn't used. """
    if 'nonconference' in tourney_group:
        with open(f'paper/table_{group}_natl.tex', 'w') as table:
            for tourney, description in tourney_group.items():
                if tourney.rstrip('_') not in tourney_group['nonconference']:
                    continue
                _write_tex_table_row(table, description.get('title', tourney), description.get('years', None),
                                     description.get('use_suffix', True) and tourney_group['suffix'])
            table.write(r'\bottomrule')
        with open(f'paper/table_{group}_conf.tex', 'w') as table:
            for tourney, description in tourney_group.items():
                if tourney in ('comment', 'suffix', 'nonconference'):
                    continue
                if tourney.rstrip('_') in tourney_group['nonconference']:
                    continue
                _write_tex_table_row(table, description.get('title', tourney), description.get('years', None),
                                     description.get('use_suffix', True) and tourney_group['suffix'])
            table.write(r'\bottomrule')
    else:
        with open(f'paper/table_{group}.tex', 'w') as table:
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


def write_plots_for_paper() -> None:
    write_plot_file_round('bbm/D1/winloss.csv', 'bbm/D1/winlossRd2.tex', lambda r, c: c - r != 8)
    write_plot_file_round('bbw/D1/winloss.csv', 'bbw/D1/winlossRd2.tex', lambda r, c: c - r != 8)
    write_simple_plot_file('winloss.csv', 'winlosssimpleplot.tex')


def describe_weighted_reseed(reseed_file: str) -> None:
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


if __name__ == '__main__':
    with open('tourneys.json') as _json_file:
        _tourneys = json.load(_json_file)
    analyze_overall(_tourneys)
    # university.check_team_name_starts()

'''
S(z) = 1/(1+e^{-z})
1-S(z) = e^{-z}/(1+e^{-z}) = 1/(e^z+1)
p(x) = S(mx+b). b=0
L(a,p) = - ( a log p + (1-a) log (1-p) )
L(a(x),p(x)) = - ( a(x) log p(x) + (1-a(x)) log (1-p(x) )
L(w(x),p(x)) = - w(x) log p(x) = w(x) log (1+e^(-mx))
L(l(x),p(x)) = - l(x) log ( 1-p(x) ) = l(x) log (1+e^(mx))

L(w(x),p(x))_m = -xe^(-mx)w(x) / (1+e^(-mx))
L(l(x),p(x))_m = xe^(mx)l(x) / (1+e^(mx))

p(-1)=S(-m)=1/(1+e^m))
e^m = 1/p(-1) - 1
m = ln(1/p(-1) - 1)

'''

# my edits
# https://en.wikipedia.org/w/index.php?title=1981_NCAA_Division_III_basketball_tournament&diff=prev&oldid=1219802469
# https://en.wikipedia.org/w/index.php?title=1977_Pacific_Coast_Athletic_Association_men%27s_basketball_tournament&diff=prev&oldid=1219661417

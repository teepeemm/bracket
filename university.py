""" A module focused on analyzing universities.

The big goal of this is the function `normalize_team_name`, which aims
to consolidate all team names from Wikipedia into a unique identify-able string.  An important note on that function is
that expediency may mean that we don't use a traditional way of referring to a team.  From a programming point of view,
the easiest and most consistent approach seems to be to expand all abbreviations, and then remove unnecessary words.

The only abbreviations left are A&M (and similar), Tech, SCAD and SUNY.  (I think.)

Note that Simon Fraser U in British Columbia is the only non-US university in the NCAA. """

from __future__ import annotations

import collections
import json
import re
import typing

__author__ = 'Timothy Prescott'
__version__ = '2024-06-24'


class Flags(typing.NamedTuple):
    """ Some short booleans (and one sometimes string) that we may pass in """
    is_tennis: bool = False
    is_professional: bool = False
    tourney: str = ''
    num_teams: int = -1
    multi_elim: bool = False
    is_national: bool = False


_team_name_from = collections.defaultdict(set)
""" Observed team names that become a particular team name. Used by `check_team_name_starts`. """

timezones: dict[str, tuple[str, ...]] = {
    'Eastern': ('CT', 'DC', 'DE', 'FL', 'GA', 'IN', 'KY', 'MA', 'MD', 'ME', 'MI', 'NC', 'NH', 'NJ', 'NY', 'OH', 'ON',
                'PA', 'QC', 'RI', 'SC', 'TN', 'VA', 'VT', 'WV'),
    'Central': ('AL', 'AR', 'IA', 'IL', 'KS', 'LA', 'MB', 'MN', 'MO', 'MS', 'ND', 'NE', 'OK', 'SD', 'TX', 'WI'),
    'Saskatchewan': ('SK',),  # CST
    'Mountain': ('AB', 'CO', 'ID', 'MT', 'NM', 'UT', 'WY'),
    'Arizona': ('AZ',),  # MST
    'Pacific': ('CA', 'NV', 'OR', 'WA', 'BC'),
    'Alaska': ('AK',),
    'Hawaii': ('HI',),
}
""" We oversimplify and put the entirety of a state into one timezone.  Indiana goes into Eastern.
The provinces are those that have an NHL team (also MLB and NBA, but that's redundant). """

state_abbrevs: dict[str, str] = {
    'AL': 'Alabama', 'ALA': 'Alabama', 'AK': 'Alaska', 'ALAS': 'Alaska',
    'AZ': 'Arizona', 'ARIZ': 'Arizona', 'AR': 'Arkansas', 'ARK': 'Arkansas',
    'BC': 'British Columbia',
    'CA': 'California', 'CAL': 'California', 'CALIF': 'California', 'CO': 'Colorado', 'COLO': 'Colorado',
    'CT': 'Connecticut', 'CONN': 'Connecticut',
    'DC': 'District of Columbia', 'DE': 'Delaware',
    'FL': 'Florida', 'FLA': 'Florida',
    'GA': 'Georgia',
    'HI': 'Hawaii', 'HAW': 'Hawaii',
    'ID': 'Idaho', 'IL': 'Illinois', 'ILL': 'Illinois', 'IN': 'Indiana', 'IND': 'Indiana', 'IA': 'Iowa',
    'KS': 'Kansas', 'KAN': 'Kansas', 'KY': 'Kentucky',
    'MB': 'Manitoba',
    'ME': 'Maine', 'MD': 'Maryland', 'MA': 'Massachusetts', 'MASS': 'Massachusetts',
    'MI': 'Michigan', 'MICH': 'Michigan', 'MN': 'Minnesota', 'MINN': 'Minnesota',
    'MS': 'Mississippi', 'MISS': 'Mississippi', 'MO': 'Missouri', 'MT': 'Montana', 'MONT': 'Montana',
    'NEB': 'Nebraska', 'NV': 'Nevada', 'NH': 'New Hampshire', 'NJ': 'New Jersey',
    'NM': 'New Mexico', 'NMEX': 'New Mexico', 'NY': 'New York', 'NC': 'North Carolina',
    'ND': 'North Dakota',
    'ON': 'Ontario',
    'OH': 'Ohio', 'OK': 'Oklahoma', 'OKLA': 'Oklahoma', 'OR': 'Oregon', 'ORE': 'Oregon',
    'PA': 'Pennsylvania', 'PENN': 'Pennsylvania',
    'QC': 'Quebec',
    'RI': 'Rhode Island',
    'SC': 'South Carolina',  # USC is ambiguous, but handled elsewhere
    'SD': 'South Dakota',
    'SK': 'Saskatchewan',
    'TN': 'Tennessee', 'TENN': 'Tennessee', 'TX': 'Texas', 'TEX': 'Texas',
    'WA': 'Washington', 'WASH': 'Washington',
    'WV': 'West Virginia', 'WVA': 'West Virginia', 'WVU': 'West Virginia', 'WESTVIRGINIA': 'West Virginia',
    'WI': 'Wisconsin', 'WIS': 'Wisconsin', 'WISC': 'Wisconsin', 'WY': 'Wyoming',
    'VT': 'Vermont', 'VA': 'Virginia',
    # not alphabetical at the end so that WV is checked before VA
}
""" A few states are omitted because they could be ambiguous. """

spaced_abbrevs: frozenset[str] = frozenset(['BC', 'DC', 'NH', 'NJ', 'NM', 'NY', 'NC', 'ND', 'SC', 'SD', 'WV'])
""" These states have a space in their expansion, so we have to be a bit careful. """

other_state_abbrevs: dict[str, str] = {
    'AB': 'Alberta',  # Alabama Birmingham
    'LA': 'Louisiana',  # Los Angeles
    'NE': 'Nebraska',  # Northeast
    'UT': 'Utah'  # University of TN or TX
}
""" These were not included in `spaced_abbrevs` because the abbreviation could be ambiguous. """

all_state_abbrevs = state_abbrevs | other_state_abbrevs

all_states = list(all_state_abbrevs.values())

other_abbrevs: dict[str, str] = {
    r'U\.S': 'US',  # before U and S
    'SE': 'Southeast', 'SW': 'Southwest', 'NW': 'Northwest',  # NE can be Nebraska
    'So': 'Southern', 'No': 'Northern', 'Ft': 'Fort', 'Atl': 'Atlantic',
    'E': 'East', 'W': 'West', 'N': 'North', 'S': 'South',
    'C': 'Central', 'Cen': 'Central', 'Cent': 'Central', 'Mt': 'Mount', 'Isl': 'Island', 'Pt': 'Point',
    'TAMU': 'Texas A&M', "Int'l": 'International', "Inter'l": 'International', "Hawai'i": 'Hawaii',
    r'Cal(\.|ifornia)? St(\.|\b|ate)': 'California State', '^CSU *': 'California State ', 'LSU': 'Louisiana State',
    'Sch': 'School', 'U': 'University', 'Univ': 'University', 'Col': 'College', 'Coll': 'College',
    'Pitt': 'Pittsburgh', 'Poly': 'Polytechnic', 'Caro': 'Carolina',
    'Wm': 'William', 'Bros': 'Brothers', 'JWU': 'Johnson and Wales', 'BYU': 'Brigham Young', 'Jeff': 'Jefferson',
    'Mtl': 'Montreal',
    'Tech': 'Tech'  # eliminates punctuation
}
r""" This will be: `name = re.sub(r'\b'+key+r'(\.|\b)', value, name)`. """

with open('team_renames.json', encoding='utf-8') as _json:
    _team_renames: dict[str, str] = json.load(_json)
    """ This is our last chance to rename something.  We've tried our best up to this point, but some places are too
quirky. Some quick comments about some of them:
Maryland Baltimore Co became Maryland Baltimore Colorado instead of Maryland Baltimore County
Missouri S&T became Missouri South &T instead of not changing
Post becomes Post Connecticut, but we need to be careful of Long Island Post
Different teams: Seton H[ai]ll, DePau[lw] """

_professional_renames: dict[str, dict[str, str]] = {
    'MLB': {
        'California': 'Anaheim',
        'Florida Marlins': 'Miami',
        'Los Angeles Angels': 'Anaheim',
        'Minnesota Twins': 'Minnesota',
        'Montreal': 'Washington'
    },
    'NBA': {
        'Baltimore': 'Washington',
        'Buffalo': 'Los Angeles Clippers',
        'California State Sacramento': 'Sacramento',  # fix that
        'Capital': 'Washington',
        'Cincinnati': 'Sacramento',
        'Fort Wayne': 'Detroit',
        'Kansas City': 'Sacramento',
        'Kansas City Omaha': 'Sacramento',
        'Minneapolis': 'Los Angeles Lakers',
        'New Jersey': 'Brooklyn',
        'Rochester': 'Sacramento',
        'Saint Louis': 'Atlanta',
        'San Diego': 'Los Angeles Clippers',
        'San Francisco': 'Golden State',
        'Seattle': 'Oklahoma City',
        'Syracuse': 'Philadelphia'
    },
    'NFL': {
        'Los Angeles Raiders': 'Vegas',
        'Oakland': 'Vegas',
        'Saint Louis Cardinals': 'Arizona',
        'Saint Louis Rams': 'Los Angeles Rams'
    },
    'NHL': {
        'Arizona': 'Phoenix',
        'Hartford': 'Carolina',
        'Minnesota North Stars': 'Minnesota',
        'Quebec': 'Colorado'
    },
    'WNBA': {}
}
""" Professional teams are easier to handle because there are fewer of them,
but harder because they move and rename. """

_professional_keep_team: dict[str, frozenset[str]] = {
    'MLB': frozenset(['Chicago', 'Los Angeles', 'New York']),
    'NBA': frozenset(['Los Angeles']),
    'NFL': frozenset(['Los Angeles', 'New York']),
    'NHL': frozenset(['New York']),
    'WNBA': frozenset()
}
""" Usually, a city (or state) is enough to identify a team.  But not when there are two teams """

_versions: dict[str, str] = {
    r'Alcorn( A\&M)?( State)?( Mississippi)?': 'Alcorn',
    r'App(alachian)? State( North Carolina)?': 'Appalachian',
    'Armstrong( Atlantic)?( State)?': 'Armstrong',
    'Augsburg( College)?( Minnesota)?': 'Augsburg',
    'Augusta( State)?( Georgia)?': 'Augusta',
    r'California St(\.|ate)?,? L\.?A\.?': 'California State Los Angeles',
    r"California State San B(ern\.|'dino)?": 'California State San Bernardino',
    'U?C(al(ifornia)?)? ?S(anta)? ?B(arbara)?': 'California Santa Barbara',
    r'Carroll (College|Montana)( Montana)?': 'Carroll Montana',
    r'Claremont M(udd)?( S(outh|cripps)?)?( California)?': 'Claremont Mudd Scripps',
    'Clarion( State)?( Pennsylvania)?': 'Clarion',
    'College of Charleston( South Carolina)?': 'Charleston South Carolina',
    'East(ern)? Connecticut( State)?': 'Eastern Connecticut',
    'East Central( State)?( Oklahoma)?': 'East Central Oklahoma',
    'Edinboro( State)?( Pennsylvania)?': 'Edinboro',
    'Elizabeth City( State)?( North Carolina)?': 'Elizabeth City',
    'Evergreen( State)?( Washington)?': 'Evergreen Washington',
    'FDU ?(Florham|Madison)': 'Fairleigh Dickinson',
    'Ferris Institute( Michigan)?': 'Ferris State',
    r'Frank(\.|lin)? (\&|and) Marsh(\.|all)?': 'Franklin and Marshall',
    'Grambling State( Louisiana)?': 'Grambling',
    'Hampton( Institute)?( Virginia)?': 'Hampton',
    'Hastings( College)?( Nebraska)?': 'Hastings',
    'U? ?I(llinois)? ?C(hicago)?': 'Illinois Chicago',
    'I(ndiana)?U(niversity)? East( Indiana)?': 'Indiana East',
    'Indiana University East': 'Indiana East',
    'IU Southeast( Indiana)?': 'Indiana Southeast',
    'Jordan( College)?( Michigan)?': 'Jordan',
    'Liberty( Baptist)?( Virginia)?': 'Liberty',
    r'L(ong )?I(sland )?U?[- ]? ?Post( \(?N(ew )?Y(ork)?\)?)?': 'Long Island Post',
    r'C(\.|entral)? ?W(\.|est)? ?Post( \(?N(ew )?Y(ork)?\)?)?': 'Long Island Post',
    'Long Island Central West Post': 'Long Island Post',
    'L(ong)? ?I(sland)? ?(U(niversity)?)?( Brooklyn)?': 'Long Island',
    'U?LA? Lafayette': 'Louisiana Lafayette',
    r'Loyola( University)? \(?(Chicago|Illinois)\)?': 'Loyola Chicago',
    r'Loyola \(?(Los Angeles|California)\)?': 'Loyola Marymount',
    'Mansfield( State)?( Pennsylvania)?': 'Mansfield',
    r'Maryland E(\.|ast(ern)?)? Shore': 'Maryland Eastern Shore',
    'Memphis( State)?( Tennessee)?': 'Memphis',
    'Midland( Lutheran)?( Nebraska)?': 'Midland',
    'Midwestern( State)?( Texas)?': 'Midwestern State Texas',
    'Miles( College)?( Alabama)?': 'Miles',
    'Millersville( State)?( Pennsylvania)?': 'Millersville',
    'Morris Harvey( West Virginia)?': 'Charleston West Virginia',
    'New Haven( State)?( Connecticut)?': 'New Haven',
    'New Mexico A&M( State)?': 'New Mexico State',
    'Northwest(ern)? Oklahoma( State)?': 'Northwestern Oklahoma',
    'Orange State( California)?': 'California State Fullerton',
    '.*Pan American.*': 'Texas Rio Grande Valley',
    'Panhandle( A&M)?( Oklahoma)?( State)?': 'Panhandle Oklahoma',
    'George Pepperdine( California)?': 'Pepperdine',
    'Peru State( College)?( Nebraska)?': 'Peru State',
    'Philadelphia Pharmacy( Pennsylvania)?': "Saint Joseph's Pennsylvania",
    'U(niversity of the )?Sciences': "Saint Joseph's Pennsylvania",
    'Point Loma( Nazarene)?( California)?': 'Point Loma Nazarene California',
    'Prairie View( A&M)?( Texas)?': 'Prairie View',
    'SAGU( Texas)?': 'Southwestern Assemblies of God',
    'Saginaw Valley( State)?( Michigan)?': 'Saginaw Valley',
    r"Saint Joseph's \(?L\.?I\.?\)?": "Saint Joseph's Long Island",
    'Saint Catharine( College)?( Kentucky)?': 'Saint Catharine Kentucky',
    "Saint Gregory's( University)?( Oklahoma)?": "Saint Gregory's Oklahoma",
    'Slippery Rock( State)?( Pennsylvania)?': 'Slippery Rock',
    'Southeast(ern)?( State)? Oklahoma( State)?': 'Southeastern Oklahoma',
    'South(ern)? California College': 'Vanguard',
    'Southern Colorado( State)?': 'Colorado State Pueblo',
    'South(ern)? Connecticut( State)?': 'Southern Connecticut',
    'S(outhern )?N(ew )?H(ampshire)?( U(niversity)?)?': 'Southern New Hampshire',
    r'Southern (Poly|Tech)(\.|technic)?( State)?( Georgia)?': 'Southern Polytechnic',
    'S(outh)?[Ww](est(ern)?)? Oklahoma( State)?( University)?': 'Southwestern Oklahoma',
    r'S(tephen )?F\.? ?A(ustin)?( State)?( Texas)?': 'Stephen F Austin',
    '(Richard )?Stockton ?(College|University)?': 'Stockton',
    'Texas A&M CC': 'Texas A&M Corpus Christi',
    '(A&M )?Corpus Christi( Texas)?': 'Texas A&M Corpus Christi',
    'UT ?R(io)? ?G(rande)? ?(V(alley)?)?': 'Texas Rio Grande Valley',
    r'Philadelphia ((Textile)|(U(\.|niv(\.|ersity)?)?)|(College))': 'Thomas Jefferson',
    'Troy( State)?( Alabama)?': 'Troy',
    r'U\.?S\.? International( California)?': 'United States International',
    'Villa Madonna( Kentucky)?': 'Thomas More',
    'Wayne( St.)? Michigan': 'Wayne State Michigan',
    r'Wash(ington )?U(\.|niv(ersity)?)?': 'Washington Saint Louis',
    r'Wayland( Baptist)?( University)?': 'Wayland Baptist',
    'Webber( International)?( Florida)?': 'Webber',
    r'West(\.|ern)? Connecticut( State)?': 'Western Connecticut',
    'William Pennsylvania( Iowa)?': 'William Penn Iowa',
    'Winston Salem( State)?( North Carolina)?': 'Winston Salem',
    'Xavier( University of)? L[Aa]': 'Xavier Louisiana',
}
""" If a university has several versions to its name, try to consolidate them here. """

_state_university: dict[str, tuple[str, ...]] = {
    'California State': ('Bakersfield', 'Chico', 'Dominguez Hills', 'East Bay', 'Fullerton', 'Northridge', 'Sacramento',
                         'San Bernardino', 'Stanislaus'),
    'California': ('Davis', 'Riverside', 'Santa Clara', 'Santa Cruz'),
    'Colorado': ('Colorado Springs',),
    'Colorado State': ('Pueblo',),
    'Indiana': ('Kokomo', 'South Bend'),
    'Southern Illinois': ('Edwardsville',),
    'Louisiana': ('Monroe',),
    'Louisiana State': ('Alexandria', 'Shreveport'),
    'Minnesota State': ('Mankato', 'Moorhead'),
    'North Carolina': ('Charlotte', 'Greensboro', 'Pembroke'),
    'Pennsylvania State': ('Abington', 'Altoona', 'Behrend', 'Berks', 'Harrisburg'),
    'SUNY': ('Binghamton', 'Brockport', 'Cortland', 'Farmingdale', 'Fredonia', 'Geneseo', 'Maritime', 'Morrisville',
             'Niagara', 'Old Westbury', 'Oneonta', 'Oswego', 'Plattsburgh', 'Potsdam', 'Purchase'),
    'Texas': ('Arlington', 'Tyler'),
    'Wisconsin': ('Eau Claire', 'Green Bay', 'La Crosse', 'Milwaukee', 'Oshkosh', 'Parkside', 'Platteville',
                  'River Falls', 'Stevens Point', 'Stout', 'Whitewater'),
}
""" This does not contain all state universities with that prefix, just the necessary ones.
Also, that city needs to not occur elsewhere. """

university_of: dict[str, str] = {
    'Albany': 'Albany',
    'AB': 'Alabama Birmingham',
    'ALR': 'Arkansas Little Rock',
    'AFS': 'Arkansas Fort Smith',
    'CCS': 'Colorado Colorado Springs',
    'CF': 'Central Florida',
    'CLA': 'California Los Angeles',
    'CSD': 'California San Diego',
    'C San Diego': 'California San Diego',
    'Indy': 'Indianapolis',
    'IS': 'Illinois Springfield',
    'M Eastern Shore': 'Maryland Eastern Shore',
    'MES': 'Maryland Eastern Shore',
    'M Saint Louis': 'Missouri Saint Louis',
    'M St. Louis': 'Missouri Saint Louis',
    'MBC': 'Maryland Baltimore County',
    'MKC': 'Missouri Kansas City',
    'MSL': 'Missouri Saint Louis',
    'NCG': 'North Carolina Greensboro',
    'NCW': 'North Carolina Wilmington',
    'NI': 'Northern Iowa',
    'NLV': 'Nevada Las Vegas',
    'SAO': 'Science and Arts Oklahoma',
    'SCA': 'South Carolina Aiken',
    'SCUS': 'South Carolina Upstate',
    'SCHO': 'US College Hockey Online',  # probably not necessary. there's also United Soccer Coaches
    'SF': 'South Florida',
    'T Arlington': 'Texas Arlington',
    'T Chattanooga': 'Tennessee Chattanooga',
    'T Dallas': 'Texas Dallas',
    'TEP': 'Texas El Paso',
    'T Martin': 'Tennessee Martin',
    'TPA': 'Texas Rio Grande Valley',
    'TSA': 'Texas San Antonio',
    'T Tyler': 'Texas Tyler',
}
""" Places that show up as U`stuff`. """

_cities_in_state: dict[str, tuple[str, ...]] = {
    'AB': ('Calgary', 'Edmonton'),
    'AL': ('Auburn',),
    'AZ': ('Mesa', 'Phoenix'),
    'BC': ('Vancouver',),
    'CA': ('Anaheim', 'Fresno', 'Golden State', 'Los Angeles', 'Sacramento', 'San Diego', 'San Francisco', 'San Jose'),
    'CO': ('Denver',),
    'GA': ('Atlanta',),
    'FL': ('Orlando', 'Tampa Bay'),
    'IL': ('Chicago',),
    'IN': ('Fort Wayne', 'Purdue'),
    'LA': ('New Orleans',),
    'MB': ('Winnipeg',),
    'MA': ('Boston', 'Worcester'),
    'MD': ('Baltimore',),
    'MI': ('Detroit',),
    'MN': ('Minneapolis', 'Saint Paul',),
    'MO': ('Saint Louis',),
    'NC': ('Charlotte',),
    'NJ': ('Rutgers',),
    'NV': ('Vegas',),
    'NY': ('Brooklyn', 'Buffalo', 'Long Island', 'Manhattan', 'SUNY'),
    'ON': ('Ottawa', 'Toronto'),
    'OH': ('Cincinnati',),
    'PA': ('Philadelphia', 'Pittsburgh',),
    'QC': ('Montreal',),
    'SK': ('Regina',),
    'TN': ('Nashville',),
    'TX': ('Austin', 'Dallas', 'Houston', 'San Antonio'),
    'VA': ('Randolph',),
    'WA': ('Seattle',),
    'WI': ('Green Bay', 'Milwaukee')
}
""" If this city appears in a university name, then we know it's in this state.
There are many more cities that could go here.
We use this only when a city shows up with multiple universities and only one state. """

universities_in_state: dict[str, tuple[str, ...]] = {
    'AK': (),
    'AL': ('Athens State', 'Birmingham Southern', 'Christian Heritage', 'Faulkner', 'Florence State', 'Huntingdon',
           'Jacksonville State', 'Miles', 'Mobile', 'Montevallo', 'Samford', 'Spring Hill', 'Stillman', 'Talladega',
           'Troy', 'Tuskegee'),
    'AR': ('Central Baptist', 'Harding', 'Henderson State', 'Hendrix', 'John Brown', 'Little Rock', 'Lyon',
           'Ouachita Baptist', 'Philander Smith'),
    'AZ': ('Grand Canyon',),
    'BC': ('Simon Fraser',),
    'CA': ('Academy of Art', 'Antelope Valley', 'Azusa Pacific', 'Biola', 'Chapman', 'Claremont Mudd Scripps',
           'Concordia Irvine', 'Frederick Taylor', 'Holy Names', 'Hope International', 'Humboldt State', 'La Verne',
           'Long Beach State', 'Loyola Marymount', 'Menlo', 'Notre Dame de Namur', 'Occidental', 'Pacific Union',
           'Pasadena', 'Pepperdine', 'Point Loma', 'Pomona Pitzer', 'Redlands', 'Saint Katherine', 'San Jose State',
           'Santa Barbara', 'Sonoma State', 'Stanford', "The Master's", 'Vanguard', 'United States International',
           'Westmont', 'Whittier', 'William Jessup'),
    'CO': ('Adams State', 'Air Force', 'Fort Lewis'),
    'CT': ('Albertus Magnus', 'Bridgeport', 'Coast Guard', 'Fairfield', 'Hartford', 'Mitchell', 'New Haven',
           'Quinnipiac', 'Yale'),
    'DE': ('Goldey Beacom', 'Wesley'),
    'DC': ('American University', 'Catholic', 'Federal City', 'Gallaudet', 'Howard'),
    'FL': ('Ave Maria', 'Barry', 'Bethune Cookman', 'Eckerd', 'Edward Waters', 'Embry Riddle', 'Flagler', 'Keiser',
           'Lynn', 'Nova Southeastern', 'Palm Beach Atlantic', 'Rollins', 'Saint Leo', 'Stetson', 'Tampa', 'Webber'),
    'GA': ('Albany State', 'Armstrong', 'Augusta', 'Berry', 'Brewton Parker', 'Clayton State',
           'Covenant', 'Dalton State', 'Emory', 'Fort Valley State', 'Kennesaw State', 'LaGrange', 'Life', 'Mercer',
           'Morehouse', 'Oglethorpe', 'Paine', 'Piedmont', 'Reinhardt', 'Savannah State', 'SCAD', 'Shorter',
           'Southern Polytechnic', 'Valdosta State', 'Young Harris'),
    'HI': ('Chaminade',),
    'ID': ('Albertson', 'Boise State', 'Lewis Clark State', 'Northwest Nazarene'),
    'IL': ('Aurora', 'Barat', 'Blackburn', 'Bradley', 'DePaul', 'Elmhurst', 'Eureka', 'Governors State', 'Greenville',
           'Knox', 'Lake Forest', 'Lewis', 'Lindenwood Belleville', 'MacMurray', 'McKendree', 'Millikin', 'North Park',
           'Olivet Nazarene', 'Quincy', 'Rockford', 'Roosevelt', 'Saint Xavier', 'Trinity International'),
    'IN': ('Ball State', 'Butler', 'Calumet', 'Canterbury', 'DePauw', 'Earlham', 'Evansville', 'Hanover', 'Manchester',
           'Rose Hulman', 'Taylor', 'Trine', 'Valparaiso', 'Wabash'),
    'IA': ('Ashford', 'Briar Cliff', 'Buena Vista', 'Clarke', 'Coe', 'Dordt', 'Drake', 'Dubuque', 'Graceland',
           'Grand View', 'Grinnell', 'Loras', 'Luther', 'Marycrest', 'Morningside', 'Mount Mercy', 'Mount Saint Clare',
           'Saint Ambrose', 'Wartburg', 'Westmar'),
    'KS': ('Baker', 'Emporia State', 'Fort Hays State', 'Friends', 'McPherson', 'MidAmerica Nazarene', 'Newman',
           'Pittsburg State', 'Saint Mary', 'Sterling', 'Tabor', 'Washburn', 'Wichita State'),
    'KY': ('Alice Lloyd', 'Bellarmine', 'Berea', 'Brescia', 'Campbellsville', 'Centre', 'Lindsey Wilson',
           'Louisville', 'Morehead State', 'Murray State', 'Pikeville', 'Spalding', 'Thomas More', 'Transylvania'),
    'LA': ('Dillard', 'Grambling', 'McNeese', 'Northwestern State', 'Nicholls State', 'Southern',
           'Southern Baton Rouge', 'Tulane'),
    'ME': ('Bates', 'Bowdoin', 'Colby', 'Husson', 'New England University', 'Westbrook'),
    'MD': ('Baltimore', 'Bowie State', 'Coppin State', 'Frostburg State', 'Goucher', 'Hood', 'Johns Hopkins',
           'McDaniel', 'Morgan State', 'Navy', 'Salisbury', 'Stevenson', 'Towson State', 'Washington Adventist'),
    'MA': ('American International', 'Amherst', 'Anna Maria', 'Assumption', 'Babson', 'Becker', 'Bentley', 'Brandeis',
           'Curry', 'Eastern Nazarene', 'Elms', 'Emerson', 'Endicott', 'Fisher', 'Fitchburg State', 'Framingham State',
           'Harvard', 'Lasell', 'Lesley', 'Lowell', 'Merrimack', 'Mount Ida', 'Nichols', 'North Adams State',
           'Pine Manor', 'Salem State', 'Stonehill', 'Suffolk', 'Tufts', 'Wellesley', 'Wentworth',
           'Western New England', 'Westfield State'),
    'MI': ('Adrian', 'Albion', 'Alma', 'Aquinas', 'Calvin', 'Cornerstone', 'Davenport', 'Ferris State', 'Finlandia',
           'Grand Valley State', 'Hillsdale', 'Jordan', 'Kalamazoo', 'Lake Superior State', 'Lawrence Tech',
           'Madonna', 'Saginaw Valley', 'Siena Heights', 'Spring Arbor'),
    'MN': ('Augsburg', 'Bemidji State', 'Bethany Lutheran', 'Carleton', 'Crown', 'Gustavus Adolphus', 'Hamline',
           'Macalester', 'Martin Luther', 'Saint Catherine', 'Saint Cloud State', 'Saint Olaf', 'Saint Scholastica',
           'Winona State'),
    'MS': ('Alcorn', 'Belhaven', 'Delta State', 'Jackson State', 'Millsaps', 'Rust', 'Tougaloo', 'William Carey'),
    'MO': ('Avila', 'Central Methodist', 'College of the Ozarks', 'Culver Stockton', 'Drury', 'Evangel', 'Fontbonne',
           'Hannibal LaGrange', 'Harris Stowe State', 'Kansas City', 'Rockhurst', 'Southwest Baptist', 'Tarkio',
           'Truman State', 'Washington Saint Louis', 'Webster', 'William Jewell', 'William Woods'),
    'MT': ('Great Falls',),
    'NE': ('Bellevue', 'Chadron State', 'Creighton', 'Doane', 'Hastings', 'Kearney State', 'Midland', 'Omaha',
           'Peru State'),
    'NV': (),
    'NH': ('Colby Sawyer', 'Daniel Webster', 'Dartmouth', 'Franklin Pierce', 'Keene State', 'New England College',
           'Plymouth State', 'Rivier', 'Saint Anselm'),
    'NJ': ('Bloomfield', 'Caldwell', 'Drew', 'Fairleigh Dickinson', 'Felician', 'Jersey City State', 'Kean',
           'Montclair State', 'Princeton', 'Ramapo', 'Rider', 'Rowan', "Saint Peter's", 'Seton Hall',
           'Stevens Tech', 'Stockton', 'Trenton State', 'Upsala', 'William Paterson'),
    'NM': ('Albuquerque', 'Santa Fe'),
    'NY': ('Adelphi', 'Army', 'Baruch', 'Canisius', 'Cazenovia', 'City Tech', 'Clarkson', 'Colgate', 'Daemen',
           'Dowling', 'Elmira', 'Fordham', 'Hamilton', 'Hartwick', 'Hobart', 'Hofstra', 'Hunter', 'Iona', 'Ithaca',
           'John Jay', 'Le Moyne', 'Lehman', 'Marist', 'Medaille', 'Medgar Evers', 'Merchant Marine', 'Mercy', 'Molloy',
           'Mount Saint Mary', 'Mount Saint Vincent', 'Nazareth', 'New Rochelle', 'Pace', 'Pratt Institute',
           'Rensselaer', 'Roberts Wesleyan', 'Rochester Institute Tech', 'Russell Sage', 'Saint Bonaventure',
           'Saint John Fisher', 'Saint Lawrence', 'Saint Rose', 'Siena', 'Skidmore', 'Southampton', 'Staten Island',
           'Stony Brook', 'Syracuse', 'Utica', 'Vassar', 'Wagner', 'Wells', 'Yeshiva'),
    'NC': ('Appalachian', 'Asheville Biltmore', 'Atlantic Christian', 'Barber Scotia', 'Barton', 'Belmont Abbey',
           'Brevard', 'Campbell', 'Catawba', 'Chowan', 'Davidson', 'Duke', 'East Carolina', 'Elizabeth City', 'Elon',
           'Fayetteville State', 'Gardner Webb', 'Guilford', 'High Point', 'Johnson Central Smith', 'Lenoir Rhyne',
           'Lees McRae', 'Livingstone', 'Mars Hill', 'Meredith', 'Methodist', 'Montreat', 'Mount Olive', 'Pfeiffer',
           'Saint Andrews', "Saint Augustine's", 'Shaw', 'Wake Forest', 'Western Carolina', 'William Peace', 'Wingate',
           'Winston Salem'),
    'ND': ('Dickinson State', 'Jamestown', 'Mary', 'Mayville State', 'Minot State', 'Valley City State'),
    'OH': ('Alfred Holbrook', 'Akron', 'Ashland', 'Baldwin Wallace', 'Bowling Green', 'Capital', 'Case Western',
           'Cedarville', 'Cleveland', 'Dayton', 'Defiance', 'Denison', 'Findlay', 'Heidelberg', 'Hiram', 'John Carroll',
           'Kent State', 'Kenyon', 'Lake Erie', 'Lourdes', 'Malone', 'Marietta', 'Mount Saint Joseph', 'Mount Union',
           'Mount Vernon Nazarene', 'Muskingum', 'Oberlin', 'Otterbein', 'Shawnee State', 'Steubenville', 'Tiffin',
           'Toledo', 'Urbana', 'Ursuline', 'Walsh', 'Wilberforce', 'Wittenberg', 'Wooster', 'Wright State',
           'Youngstown'),
    'OK': ('Bacone', 'Cameron', 'Langston', 'Mid America Christian', 'Oral Roberts', 'Panhandle State', 'Phillips',
           'Rogers State', 'Southern Nazarene', 'Tulsa'),
    'OR': ('Bushnell', 'Cascade', 'Corban', 'George Fox', 'Lewis and Clark', 'Linfield', 'Portland', 'Portland State',
           'Warner Pacific', 'Willamette'),
    'PA': ('Albright', 'Allegheny', 'Alvernia', 'Arcadia', 'Bloomsburg', 'Bucknell', 'Cabrini', 'Cairn',
           'Carnegie Mellon', 'Chatham', 'Chestnut Hill', 'Cheyney', 'Clarion', 'Clarks Summit', 'DeSales', 'Dickinson',
           'Drexel', 'Duquesne', 'East Stroudsburg', 'Edinboro', 'Elizabethtown', 'Franklin and Marshall', 'Gannon',
           'Geneva', 'Gettysburg', 'Grove City', 'Gwynedd Mercy', 'Haverford', 'Immaculata', 'Indiana Pennsylvania',
           'Jefferson', 'Juniata', 'Keystone', 'Kutztown', 'La Roche', 'La Salle', 'Lancaster Bible', 'Lebanon Valley',
           'Lehigh', 'Lock Haven', 'Lycoming', 'Mansfield', 'Mercyhurst', 'Messiah', 'Millersville', 'Misericordia',
           'Moravian', 'Mount Aloysius', 'Muhlenberg', 'Neumann', 'PennWest California', 'Point Park', 'Rosemont',
           'Saint Vincent', 'Scranton', 'Seton Hill', 'Shippensburg', 'Slippery Rock', 'Spring Garden', 'Susquehanna',
           'Swarthmore', 'Temple', 'Thiel', 'Thomas Jefferson', 'Ursinus', 'Villanova', 'Washington and Jefferson',
           'Waynesburg', 'West Chester', 'Widener', 'Wilkes'),
    'RI': ('Brown', 'Bryant', 'Johnson & Wales', 'Roger Williams', 'Salve Regina'),
    'SC': ('Charleston Southern', 'Claflin', 'Clemson', 'Coastal Carolina', 'Erskine', 'Francis Marion', 'Furman',
           'Lander', 'Limestone', 'Morris', 'Newberry', 'North Greenville', 'Presbyterian', 'Southern Wesleyan',
           'The Citadel', 'Voorhees', 'Winthrop', 'Wofford'),
    'SD': ('Black Hills State', 'Dakota State', 'Dakota Wesleyan', 'Huron', 'Mount Marty', 'Northern State',
           'Presentation', 'Sioux Falls', 'Yankton'),
    'TN': ('Carson Newman', 'Chattanooga', 'Christian Brothers', 'Crichton', 'David Lipscomb', 'Fisk',
           'Freed Hardeman', 'Knoxville', 'Lambuth', 'Lane', 'Lee', 'LeMoyne Owen', 'Lincoln Memorial', 'Lipscomb',
           'Memphis', 'Milligan', 'Rhodes', 'Sewanee', 'Trevecca Nazarene', 'Tusculum', 'Vanderbilt'),
    'TX': ('Abilene Christian', 'Angelo State', 'Baylor', 'Hardin Simmons', 'Howard Payne', 'Huston Tillotson',
           'Incarnate Word', 'Jarvis Christian', 'Lamar', 'LeTourneau', 'Lubbock Christian', 'Mary Hardin Baylor',
           'McMurry', 'Our Lady of the Lake', 'Paul Quinn', 'Prairie View', 'Rice', "Saint Edward's", 'Schreiner',
           'Southern Methodist', 'Southwestern Assemblies of God', 'Sul Ross State', 'Tarleton', 'Wayland Baptist',
           'Wiley'),
    'UT': ('Brigham Young', 'Dixie State', 'Weber State'),
    'VT': ('Castleton', 'Green Mountain', 'Lyndon State', 'Middlebury', 'Norwich', "Saint Michael's"),
    'VA': ('Averett', 'Bluefield', 'Christopher Newport', 'Eastern Mennonite', 'Emory and Henry', 'Ferrum',
           'George Mason', 'Hampden Sydney', 'Hampton', 'James Madison', 'Liberty', 'Longwood', 'Lynchburg',
           'Mary Washington', 'Norfolk State', 'Old Dominion', 'Radford', 'Richmond', 'Roanoke', 'Shenandoah',
           'Washington and Lee', 'William and Mary'),
    'WA': ('Evergreen', 'Gonzaga', 'Pacific Lutheran', 'Puget Sound', "Saint Martin's", 'Whitman', 'Whitworth'),
    'WV': ('Alderson Broaddus', 'Concord', 'Fairmont State', 'Glenville State', 'Marshall', 'Mountain State',
           'Shepherd', 'West Liberty', 'Wheeling Jesuit'),
    'WI': ('Beloit', 'Cardinal Stritch', 'Carthage', 'Edgewood', 'Lakeland', 'Lawrence', 'Marquette',
           'Milwaukee School of Engineering', 'Mount Senario', 'Northland', 'Ripon', 'Saint Norbert', 'Viterbo'),
    'WY': ()
}
""" If the university shows up in the name, then we don't need to worry about it here.  See also `_cities_in_state`. """

_conferences: frozenset[str] = frozenset([
    'A East', 'Atlantic 10', 'Atlantic Coast Conference', 'America East', 'Atlantic Hockey', 'Atlantic Sun', 'Big East',
    'Big Sky', 'Big South', 'Big Ten', 'BSC', 'C USA', 'CAA', 'Colonial Athletic Association',
    'Commonwealth Coast Conference', 'ECAC', 'ECAC Hockey', 'Hockey East', 'Horizon League', 'Ivy', 'MAAC', 'MEAC',
    'Metro Atlantic Athletic Conference', 'Mid Cont', 'Mid-American Conference', 'Midwestern Collegiate Conference',
    'Missouri Valley Conference', 'MVC', 'NAC', 'NCHC', 'NEC', 'New England Hockey Conference', 'Northeast',
    'Northeast Conference', 'OVC', 'Ohio Valley Conference', 'Patriot', 'Patriot League', 'SLC', 'SoCon', 'Southern',
    'Southland', 'Summit League', 'SWAC', 'TAAC', 'West Coast Conference'
])
""" This is not intended to be exhaustive, but for the appearances in (1) `team_rstrip_common` and
(2) `_disambiguation_match` """

_saints: frozenset[str] = frozenset(['Louis', 'Paul', 'Thomas'])
""" This is not intended to be exhaustive, but to cover occurrences of `St. (saint)`. """

can_drop = {
    'College': {'Augusta', 'Brooklyn', 'Centre', 'Culver Stockton', 'Federal City', 'Hartwick', 'Hunter', 'Ithaca',
                'Limestone', 'Madison', 'Maryville', 'Middlebury', 'Philander Smith', 'Saint Norbert', 'Smith',
                'Thomas Jefferson', 'Trinity', 'Wiley'},
    'State': {'Bloomsburg', 'Bluefield', 'Castleton', 'Central Connecticut', 'Central Missouri', 'Central Washington',
              'Cheyney', 'East Stroudsburg', 'East Tennessee', 'Eastern Illinois', 'Eastern Oregon',
              'Eastern Washington', 'Georgia Southwestern', 'Lock Haven', 'McNeese', 'Middle Tennessee',
              'Missouri Southern', 'Missouri Western', 'North Carolina A&T', 'North Texas', 'Salisbury', 'Sam Houston',
              'Southeastern', 'Southern Connecticut', 'Southern Oregon', 'Southern Utah', 'Stockton', 'Tarleton',
              'West Chester', 'West Liberty', 'Western Illinois', 'Western Kentucky',
              'Western Oregon', 'Western Washington', 'Youngstown'},
    'University': {'Arizona Christian', 'Belhaven', 'Catholic', 'Chicago State', 'Evangel', 'Freed Hardeman',
                   'Georgia State', 'Lamar', 'Life', 'Oklahoma City', 'Samford', 'Southwestern Assemblies of God',
                   'Thomas Jefferson'}
}
""" Whether we can drop the literal word at the end of a name. """

_prof_disambiguations: dict[str, dict[str, dict[str, typing.Iterable]]] = {
    'MLB': {
        'Florida': {'Marlins': ()},
        'Los Angeles': {'Angels': (), 'Dodgers': ()},
        'New York': {'Mets': (), 'Yankees': ()}
    },
    'NBA': {
        'Indiana': {'Pacers': ()},
        'Indianapolis': {'Olympians': ()},  # existing 1949--1953
        'Los Angeles': {'Clippers': (), 'Lakers': ()}
        # 'New York': {'Knicks': ()}
    },
    'NFL': {
        'Los Angeles': {'Chargers': (), 'Raiders': (), 'Rams': ()},
        'New York': {'Giants': (), 'Jets': ()},
        'Saint Louis': {'Cardinals': (), 'Rams': ()}
    },
    'NHL': {
        # 'Los Angeles': {'Kings': ()},
        'New York': {'Islanders': (), 'Rangers': ()}
    },
    'WNBA': {}
}
""" Used by `get_disambiguator`. """

with open('univ_disambiguations.json', encoding='utf-8') as _json:
    _univ_disambiguations: dict[str, dict[str, typing.Iterable[str | re.Pattern]]] \
        = json.load(_json) | {
        'Northeastern': {
            'CO': ['Northeastern Junior College'],
            'IL': ['Northeastern Golden Eagles'],
            'MA': ['Northeastern Huskies', 'Colonial Athletic Association', 'Hockey East', 'ECAC',
                   re.compile(r'Northeastern University\S')]
        },
        'Robert Morris': {
            'IL': ['Morris Eagles', 'Robert Morris University Illinois'],
            'PA': ['Morris Colonials', 'Northeast Conference', 'Atlantic Hockey',
                   re.compile(r'Robert Morris University\S')]
        },
        'Benedict': {
            'SC': ['Benedict Tigers', 'Benedict College', re.compile(r'\SBenedict(\S|\n)')]
        },
        "Saint Joseph's": {
            'Brooklyn': ["Joseph's Bears"],
            'CT': ["Joseph's Blue Jays"],
            'IN': ["St. Joseph's (IN)", "Joseph's Pumas"],
            'Long Island': ["Joseph's Golden Eagles"],
            'ME': ["Joseph's Monks"],
            'NY': [],
            'PA': ["Joseph's Hawks", 'Atlantic 10', re.compile(r"Saint Joseph's University\S")]
        },
        'Smith': {
            'MA': ['Smith Pioneers', re.compile(r'\SSmith College(\W|$)')],
            'NY': []
        }
    }
    """ These are used in `_disambiguation_match`.  If an element of the tuple is present in content, then we assume we
have that tuple's key.  We use the conferences only in non-national tournaments.
Most of this is offloaded to univ_disambiguations.json.  The ones here use a regex, which isn't valid json. """

_univ_disambiguation_defaults: dict[tuple[str, str], dict[str, typing.Iterable]] = {
    ('Miami', 'FL'): {
        'FL': ('Miami Hurricanes', 'Atlantic Coast Conference', 'Big East'),
        'OH': ('Miami Red', 'Mid-American Conference', 'NCHC')
    },
    ('Northwestern', 'IL'): {
            'IL': ('Northwestern Wildcats', 'Big Ten', re.compile(r'Northwestern University\S')),
            'LA': (), 'OH': (), 'OK': (), 'Saint Paul': ()
        },
    ('Notre Dame', 'IN'): {
        'IN': ('Fighting Irish', 'University of Notre Dame', 'Atlantic Coast Conference', 'Big East', 'Big Ten',
               'Hockey East'),
        'MD': (), 'NH': (), 'NY': (), 'OH': (), 'de Namur': ()
    },
    ('Providence', 'RI'): {
            'MT': ('University of Providence',),
            'RI': ('Providence College', 'Providence Friars', 'Big East', 'Hockey East', 'ECAC')
        },
    ('Xavier', 'OH'): {
        'OH': ('Musketeers', 'Cincinnati', 'Atlantic 10', 'Midwestern Collegiate Conference', 'Big East'),
        'LA': ('Gold Rush', 'Gold Nuggets', 'Xavier University of Louisiana')
    }
}
""" Disambiguations that have a (well known) default to fall back to if nothing else is present """

TOTAL_DISAMBIGUATIONS: typing.Final[int] = len(_univ_disambiguations) + len(_univ_disambiguation_defaults) \
    + sum((len(teams) for teams in _prof_disambiguations.values())) + 2
# The last +2 is because of USC and Thomas Jefferson U


def _disambiguation_match(phrase: str | re.Pattern, content: str, is_national: bool) -> bool:
    """ :param phrase:
    :param content:
    :param is_national:
    :return: Whether the phrase occurs in the content. """
    if isinstance(phrase, str):
        if is_national and phrase in _conferences:
            return False
        return phrase in content
    return bool(phrase.search(content))


def _disambiguation_literal(uni: str, st: str, content: str) -> bool:
    """ :return: Whether '{uni} (st)' occurs in content, for various ideas of 'st'. """
    if uni.removeprefix('Saint') not in content:
        return False
    if re.search(rf'{uni.removeprefix("Saint ")} \(?(?i:{st})\b', content) or \
            re.search(rf'{uni.removeprefix("Saint ")} \(?{all_state_abbrevs.get(st, st)}\b', content):
        return True
    if st in state_abbrevs:
        state = state_abbrevs[st]
        for st_, state_ in state_abbrevs.items():
            if state == state_ and re.search(rf'{uni.removeprefix("Saint ")} \(?(?i:{st_})\b', content):
                return True
    return False


def get_disambiguating_phrases(uni: str,
                               disambiguation: dict[str, typing.Iterable[str | re.Pattern]],
                               content: str,
                               is_national: bool) -> set[str]:
    """ Filter phrases to identify what could disambiguate a given university """
    disambiguating_phrases = set()
    for st, phrases in disambiguation.items():
        if _disambiguation_literal(uni, st, content) or \
                any((_disambiguation_match(phrase, content, is_national) for phrase in phrases)):
            disambiguating_phrases.add(st)
    return disambiguating_phrases


def get_disambiguator(content: str, flags: Flags) -> dict[str, dict[str, str]]:
    """ In `normalize_team_name`, we will append a disambiguation phrase (often a state) to the end of an ambiguous
    university """
    disambiguator: dict[str, dict[str, str]] = {
        'suffix': {},
        'replacement': {
            'USC Aiken': 'South Carolina Aiken',
            'USC Spartanburg': 'South Carolina Upstate',
            'USC Upstate': 'South Carolina Upstate'
        }
    }
    _disambiguations: dict[str, dict[str, typing.Iterable[str | re.Pattern]]]\
        = _prof_disambiguations[flags.tourney.rstrip('_')] if flags.is_professional else _univ_disambiguations
    # USC usually means Trojans (and definitely in a bracket). That will override
    if 'Gamecocks' in content or 'South Car' in content:
        disambiguator['replacement']['USC'] = 'South Carolina'
    if 'Trojans' in content or 'Southern Cal' in content \
            or re.search('Pac(ific)?-(8|10|12) Conference', content, flags=re.IGNORECASE):
        disambiguator['replacement']['USC'] = 'Southern California'
    if 'Thomas Jefferson University' in content or 'Philadelphia University' in content \
            or 'Jefferson Rams' in content or 'Philadelphia Rams' in content:
        disambiguator['replacement']['Philadelphia'] = 'Thomas Jefferson'
    for uni, disambiguation in _disambiguations.items():
        disambiguating_phrases = get_disambiguating_phrases(uni, disambiguation, content, flags.is_national)
        if len(disambiguating_phrases) == 1:
            st = disambiguating_phrases.pop()
            disambiguator['suffix'][uni] = f'{uni} {all_state_abbrevs.get(st, st)}'
    if not flags.is_professional:
        for (uni, default_st), disambiguation in _univ_disambiguation_defaults.items():
            disambiguating_phrases = get_disambiguating_phrases(uni, disambiguation, content, flags.is_national)
            if not disambiguating_phrases:
                disambiguating_phrases.add(default_st)
            if len(disambiguating_phrases) == 1:
                st = disambiguating_phrases.pop()
                disambiguator['suffix'][uni] = f'{uni} {all_state_abbrevs.get(st, st)}'
    return disambiguator


_professional_states: dict[str, str] = {
    'Carolina': 'NC',
    'Columbus': 'OH',
    'Jacksonville': 'FL',
    'Miami': 'FL',
    'New England': 'MA',
    'Oakland': 'CA',
    'Rochester': 'NY',
}
""" The state that a professional team plays in. """


def get_state(team: str, group: str) -> str:
    """ The state where a team is located. """
    if not team:
        return ''
    if group == 'professional' and team == 'Washington':
        return all_state_abbrevs['DC']
    for state, universities in universities_in_state.items():
        if team in universities:
            return all_state_abbrevs[state]
    for state in all_states:
        if state in team:
            return state
    for state, cities in _cities_in_state.items():
        for city in cities:
            if city in team:
                return all_state_abbrevs[state]
    if group == 'professional':
        return all_state_abbrevs[_professional_states[team]]
    return ''


standard_time: dict[str, dict[str, str]] = {
    'Arizona': {
        'standard': 'Mountain',
        'daylight': 'Pacific'
    },
    'Saskatchewan': {
        'standard': 'Central',
        'daylight': 'Mountain'
    }
}
""" These don't observe DST. """


def get_timezone(team: str, group: str) -> str:
    """ The timezone (of the state) where a team is located. See the comments on `timezones` """
    team_state = get_state(team, group)
    if not team_state:
        return ''
    if team_state in standard_time:
        # these seasons are (almost) entirely one side or another of DST
        if group in ('bbm', 'bbw', 'ih'):
            return standard_time[team_state]['standard']
        if group in ('baseball', 'softball'):
            return standard_time[team_state]['daylight']
        return team_state
    for timezone, state_tuple in timezones.items():
        for state in state_tuple:
            if all_state_abbrevs[state] == team_state:
                return timezone
    raise ValueError(f'{team} ({team_state}) does not have a state')


def team_rstrip_common(value: str) -> str:
    """ Remove various suffixes from a team name """
    value = re.sub(r''' ,? (^|\b|\s) \s*       # leading items to ignore
                                (\()?                  # opening paren 
                                ( \d* \s* OT           # overtime
                                | \s* P[SK]O?'?s? \s*  # penalty kicks/shots (soccer & hockey)
                                | CK                   # corner kicks (see soccer/NCAA/1966)
                                | p(en)?(\.|\b)        # penalty
                                | a\.?e\.?t\.?         # after extra time (usually in soccer)
                                | \d+ \ ? innings
                                | \#?\d                # ranking
                                | \d+\ \d+(\ \d+)?     # a team's record (hyphens were removed earlier)
                                | forfeit | vacated | bye | vacant | cancelled
                                | \*
                                | [,;/] \s*
                                )+
                                (?(2)\)|)              # closing paren (if opening was present)
                                $           ''', '', value, flags=re.IGNORECASE | re.VERBOSE)
    for conf in _conferences:
        if conf in value:  # the conditional is not strictly necessary, but gives a x30 speedup at this point
            # 1994 Women's Volleyball: Texas Southern has record of "?"
            value = re.sub(r'\s*\(' + conf + r'(\.?,?\s+(\d+ \d+( \d+)?|\?))?\)$', '', value)
    return value


def team_remove_suffix(value: str) -> str:
    """ Maybe remove the state from the end of the team name.  Sometimes Wikipedia has <College> <State> to help
    locate less known colleges.  We'll try to drop that. Unless it causes ambiguity. """
    for st, cities in _cities_in_state.items():
        if any((city in value for city in cities)):
            return value.removesuffix(all_state_abbrevs[st]).rstrip()
    for st, unis in universities_in_state.items():
        state = all_state_abbrevs[st]
        if value.endswith(state):
            potential = value.removesuffix(state).rstrip()
            if potential in unis:
                return potential
    for word, potentials in can_drop.items():
        if value.endswith(' ' + word):
            potential = value.removesuffix(' ' + word)
            if potential in potentials:
                value = potential
    for state in all_states:
        if value.endswith(' ' + state):
            potential = value.removesuffix(' ' + state)
            if get_state(potential, '') == state:
                value = potential
    return value


def team_remove_prefix(value: str) -> str:
    """ Remove various prefixes from a team name. """
    value = value.removeprefix('at ').removeprefix('Canceled due to').removeprefix('COVID 19 pandemic')
    value = re.sub(r'^\(?(#|No\. ?)?\d+\)? ', '', value)
    return value


def _get_spaced_abbrev(match) -> str:
    abbr = match.group(1) + match.group(2)
    if abbr in spaced_abbrevs:
        return all_state_abbrevs[abbr]
    return match.group(0)


def normalize_professional_name(team_name: str, tourney: str) -> str:
    """ Transform a professional team name (which has gone through `normalize_team_name`) into a standard form. """
    value = team_name
    value = value.replace('LA ', 'Los Angeles ')
    for cities in _cities_in_state.values():
        for city in cities:
            if city in value and city not in _professional_keep_team[tourney.rstrip('_')]:
                value = city
    if tourney.rstrip('_') in _professional_renames and value in _professional_renames[tourney.rstrip('_')]:
        value = _professional_renames[tourney.rstrip('_')][value]
    if (value, tourney) in ():
        print(team_name, tourney, '=>', value)
        # breakpoint()
    return value


def _expand_abbrevs(value: str) -> str:
    """ :param value:
    :return: `value`, with various abbreviations expanded. """
    value = re.sub(r'\s\s+', ' ', value)
    value = re.sub(r'^Mt\.? ', 'Mount ', value)
    value = re.sub(r'^(Mount )?St(\.|\b)', r'\1Saint', value)
    for saint in _saints:
        if saint in value:
            value = re.sub('St.? ' + saint + r'\b', 'Saint ' + saint, value)
    value = re.sub(r'\bU?([A-Z])\.?([A-Za-z]{1,4})(\.|\b)',
                   lambda m: state_abbrevs.get(m.group(1) + m.group(2).upper(), m.group(0)), value).strip()
    value = re.sub(r'(?<=\s)\(([A-Z][A-Za-z])\.?\)$',
                   lambda m: other_state_abbrevs.get(m.group(1).upper(), m.group(0)), value)
    value = re.sub(r'\b([A-Z])\.? ([A-Z])(\.|\b)', _get_spaced_abbrev, value)
    return value


def _expand_more_abbrevs(value: str) -> str:
    """ :param value:
    :return: `value`, with more abbreviations expanded. """
    value = value.replace(',', '')
    for state in all_states:
        if state in value:
            value = re.sub(state + r' St(\.|\b)', state + ' State', value)
    for k, v in other_abbrevs.items():
        value = re.sub(r'\b' + k + r'(\.|\b)\s*', v + ' ', value).rstrip()
    for st, cities in _cities_in_state.items():
        for city in cities:
            value = value.replace(' (' + city + ')', ' ' + all_state_abbrevs[st])
    # drop parens for a trailing state
    value = re.sub(r'\s*\((.*)\)$',
                   lambda m: ' ' + m.group(1) if m.group(1) in all_states else m.group(0), value)
    value = re.sub(r'\s\s+', ' ', value)
    value = re.sub(r'St\.?$', 'State', value)  # this comes before or after the trailing <state>
    value = team_remove_suffix(value)
    value = re.sub(r'St\.?$', 'State', value)
    return value


def normalize_team_name(team_name: str, disambiguator: dict) -> str:
    """ Transform a university's team name into a standard form. This is the most important function of the module. """
    value = team_name
    # start by getting this into ascii (but no hyphens)
    value = re.sub(r'[-\u2010-\u2015\u2212]', ' ', value)  # various hyphens
    value = re.sub('[ʻ’]', "'", value)  # leaning single quotes
    value = value.replace('é', 'e')
    for state, city_tuple in _state_university.items():
        for city in city_tuple:
            if city in team_name:
                return f'{state} {city}'
    value = team_remove_prefix(value)
    value = team_rstrip_common(value)
    for_set = value  # to eventually add to _team_name_from
    value = _expand_abbrevs(value)
    for abbrev, expanded in university_of.items():
        if value == 'U' + abbrev:
            _team_name_from[expanded].add(for_set)
            return expanded
    # Pennsylvania has two weird cases
    if 'California' in value and 'Pennsylvania' in value:
        return 'PennWest California'
    if 'Indiana' in value and 'Pennsylvania' in value:
        return 'Indiana Pennsylvania'
    value = _expand_more_abbrevs(value)
    for regex, output in _versions.items():
        if re.fullmatch(regex, value):
            _team_name_from[output].add(for_set)
            return output
    value = disambiguator.get(value, value)
    if 'Oklahoma' in value and 'State' in value and value != 'Oklahoma State':
        value = value.replace(' State', '')  # OK has a bunch of 'OK State <direction>'
    value = _team_renames.get(value, value)  # use _team_renames if the key is there
    _team_name_from[value].add(for_set)
    # this is a good time to stop to examine how a questionable value arose
    if value in ():  #
        print(team_name, '=>', value)
        # breakpoint()
    return value


def check_team_name_starts():
    """ Analyze `_team_name_from` """
    print('number of teams:', len(_team_name_from))
    print('avg number of names:', sum((len(t) for t in _team_name_from.values()))/len(_team_name_from))
    print('worst:')
    print(max(((len(t), value, t) for value, t in _team_name_from.items())))
    print(len(_team_name_from['Long Island']), _team_name_from['Long Island'])
    print(len(_team_name_from['Long Island Post']), _team_name_from['Long Island Post'])
    # breakpoint()

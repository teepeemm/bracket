
'use strict';

const svgNamespace = 'http://www.w3.org/2000/svg';
const timezones = {
    'Eastern': ['Connecticut', 'District of Columbia', 'Delaware', 'Florida', 'Georgia', 'Indiana', 'Kentucky', 'Maine',
        'Maryland', 'Massachusetts', 'Michigan', 'New Hampshire', 'New Jersey', 'New York', 'North Carolina', 'Ohio',
        'Ontario', 'Pennsylvania', 'Quebec', 'Rhode Island', 'South Carolina', 'Tennessee', 'Virginia', 'Vermont',
        'West Virginia'],
    'Central': ['Alabama', 'Arkansas', 'Iowa', 'Illinois', 'Kansas', 'Louisiana', 'Manitoba', 'Minnesota', 'Missouri',
        'Mississippi', 'North Dakota', 'Nebraska', 'Oklahoma', 'South Dakota', 'Texas', 'Wisconsin'],
    'Saskatchewan': ['Saskatchewan'], // CST
    'Mountain': ['Alberta', 'Colorado', 'Idaho', 'Montana', 'New Mexico', 'Utah', 'Wyoming'],
    'Arizona': ['Arizona'], // MST
    'Pacific': ['California', 'Nevada', 'Oregon', 'Washington', 'British Columbia'],
    'Alaska': ['Alaska'],
    'Hawaii': ['Hawaii'],
    'Unknown': ['Unknown'],
};

const tournamentsOfGroup = {};
const contentsOfFile = {};
const unisInState = {};

Object.values(timezones).forEach( (arr) => arr.forEach( (state) => unisInState[state] = [] ) );

processFile('state.csv', putUnisInState);
processFile('professional/state.csv', putUnisInState);

document.addEventListener('DOMContentLoaded', getQuery);

/** Use the search portion of the url to set the values of the widgets. Only happens onload. */
function getQuery() {
    const searchParams = new URLSearchParams(document.location.search);
    if ( searchParams.has('file') ) {
        setFileToPlot(searchParams.get('file'));
    }
    if ( searchParams.has('x') ) {
        document.getElementById('x').value = searchParams.get('x');
    }
    if ( searchParams.has('y') ) {
        document.getElementById('y').value = searchParams.get('y');
    }
    if ( searchParams.get('individuate') === 'true' ) {
        document.getElementById('individuate').checked = true;
    }
    if ( searchParams.has('search') ) {
        document.getElementById('search').value = searchParams.get('search');
    }
    replot();
    addChangeListeners();
}

function addChangeListeners() {
    ['individuate', 'filter', 'x', 'y']
        .forEach( (id) => document.getElementById(id).addEventListener('change', replot) );
    document.getElementById('graph').addEventListener('change', graphChange);
    document.getElementById('group').addEventListener('change', groupChange);
    document.getElementById('grouper').addEventListener('change', grouperChange);
    document.getElementById('search').addEventListener('change', searchChange);
    document.getElementById('tournament').addEventListener('change', tournamentChange);
}

/** Use the state of the widgets to construct the search portion of the url, so that {@link getQuery}() will get
 *  back to this state. */
function setQuery() {
    let query = 'file=' + getFileToPlot() + '&x=' + document.getElementById('x').value + '&y='
        + document.getElementById('y').value;
    if ( document.getElementById('individuate').checked ) {
        query += '&individuate=true';
    }
    if ( document.getElementById('search').value ) {
        query += '&search=' + document.getElementById('search').value;
    }
    window.history.pushState(null, '', './?'+query);
}

/** @return {string} What file should be used, according to the current settings */
function getFileToPlot() {
    let file = '';
    const group = document.getElementById('group').value;
    if ( group !== 'all' ) {
        file = group+'/';
        const tourney = document.getElementById('tournament').value;
        if ( tourney !== 'all' ) {
            file += tourney+'_';
        }
    }
    const graph = document.getElementById('graph').value;
    if ( graph === 'seed_v_fraction' ) {
        file += 'winloss.csv';
    } else if ( graph === 'tourneyData' ) {
        file += 'group_betas.csv';
    } else {
        const grouper = document.getElementById('grouper').value;
        if ( grouper !== 'none' ) {
            file += grouper + '_';
        }
        file += 'reseed.csv';
    }
    return file;
}

/** The inverse operation of {@link getFileToPlot}().  Sets the widgets according to the input.
 *  @param {string} file */
function setFileToPlot(file) {
    let group, rest;
    if ( file.includes('/') ) {
        [group, rest] = file.split('/', 2);
        document.getElementById('group').value = group;
        groupChange();
        file = rest;
    }
    let graph, grouper;
    if ( file.endsWith('winloss.csv') ) {
        graph = 'seed_v_fraction';
        file = file.slice(0, -'winloss.csv'.length);
    } else if ( file.endsWith('group_betas.csv') ) {
        graph = 'tourneyData';
        file = file.slice(0, -'group_betas.csv'.length);
    } else if ( file.endsWith('reseed.csv') ) {
        graph = 'x_v_y';
        file = file.slice(0, -'reseed.csv'.length);
        ['conf', 'state', 'tz'].forEach( (option) => {
            if ( file.endsWith(option+'_') ) {
                grouper = option;
                file = file.slice(0, -option.length-1);
            }
        });
    }
    if ( group && file && file.endsWith('_') ) {
        const tourney = file.slice(0, -1);
        document.getElementById('tournament').value = tourney;
        tournamentChange();
    }
    document.getElementById('graph').value = graph;
    graphChange();
    if ( graph === 'x_v_y' ) {
        document.getElementById('grouper').value = grouper;
        grouperChange();
    }
}

/** Redraw the graph */
function replot() {
    const file = getFileToPlot();
    const graph = document.getElementById('graph').value;
    const plotter = graph === 'seed_v_fraction' ? winLossPlotter : scatterPlotter;
    processFile(file, plotter);
    setQuery();
}

/** When the #group selector changes */
function groupChange() {
    const group = document.getElementById('group').value;
    const tourneySelector = document.getElementById('tournament');
    document.getElementById('grouper').value = 'none';
    toggleWidget(tourneySelector, group !== 'all');
    toggleWidget(document.querySelector('#graph option[value="tourneyData"]'), group !== 'all');
    toggleWidget(document.querySelector('#grouper [value="conf"]'), group !== 'all');
    tourneySelector.value = 'all';
    if ( group !== 'all' ) {
        if ( group in tournamentsOfGroup ) {
            listTournaments(group);
        } else {
            processFile(group+'/group_betas.csv', getTournaments);
        }
    }
    tournamentChange();
}

/** Put the available tournaments into the #tournament selector
 *  @param {string} group */
function listTournaments(group) {
    const tourneyLister = document.getElementById('tournament');
    while ( tourneyLister.children.length > 1 ) {
        tourneyLister.removeChild(tourneyLister.children[1]);
    }
    tourneyLister.append(...tournamentsOfGroup[group].map( (tourney) => {
        const option = document.createElement('option');
        option.setAttribute('value', tourney);
        option.textContent = tourney;
        return option;
    }));
}

/** When the #tournament selector changes */
function tournamentChange() {
    const tourney = document.getElementById('tournament').value;
    const groupByTourney = document.querySelector('#grouper option[value="conf"]');
    const tourneyDataOption = document.querySelector('#graph option[value="tourneyData"]');
    toggleWidget(groupByTourney, tourney === 'all');
    toggleWidget(tourneyDataOption, tourney === 'all');
    if ( tourney !== 'all' && document.getElementById('graph').value === 'tourneyData' ) {
        document.getElementById('graph').value = 'seed_v_fraction';
    }
    graphChange();
}

/** When the #graph selector changes */
function graphChange() {
    const graph = document.getElementById('graph').value;
    document.getElementById('seed_v_fraction').style.display = 'none';
    document.getElementById('x_v_y').style.display = 'none';
    if ( graph === 'tourneyData' ) {
        document.getElementById('x').value = 1;
        document.getElementById('y').value = 2;
    } else {
        document.getElementById(graph).style.display = 'block';
    }
    maybeUpdateFilters();
    replot();
}

/** When the #grouper selector changes */
function grouperChange() {
    maybeUpdateFilters();
    replot();
}

/** Highlight a search result */
function searchChange() {
    const search = document.getElementById('search');
    Array.from(document.querySelectorAll('svg circle[fill="red"]')).forEach( (circle) =>
        setElementAttributesNS(circle, {'stroke': 'black', 'fill': 'black', 'r': 2}),
    );
    if ( search.value.length < 4 ) {
        return;
    }
    setElementAttributesNS(document.querySelector('svg circle[title="'+search.value+'"]'),
        {'stroke': 'red', 'fill': 'red', 'r': 3});
}

/** Wait until the universities have loaded, and then {@link updateFiltersUsing}(string[]) */
function maybeUpdateFilters() {
    const graph = document.getElementById('graph').value;
    if ( graph !== 'x_v_y' ) {
        return;
    }
    const file = getFileToPlot();
    if ( file in contentsOfFile ) {
        updateFiltersUsing(contentsOfFile[file].split('\n').slice(1).filter(getStringLength)
            .map( (line) => line.split(',') ).filter(rowNonTrivial).map( (row) => row[0] ));
    } else {
        setTimeout(maybeUpdateFilters, 100);
    }
}

/** @param {string[]} universities */
function updateFiltersUsing(universities) {
    const graph = document.getElementById('graph').value;
    if ( graph !== 'x_v_y' ) {
        return;
    }
    const usedStatesObj = {};
    if ( document.getElementById('grouper').value === 'state' ) {
        universities.forEach( (state) => usedStatesObj[state || 'Unknown'] = 1 );
    } else if ( document.getElementById('grouper').value === 'none' ) {
        universities.forEach( (university) => {
            const stateUni = Object.entries(unisInState).find( ([state, unis]) => unis.includes(university) )
                || ['Unknown'];
            const state = stateUni[0];
            usedStatesObj[state] = 1;
        });
    }
    const usedStates = Object.keys(usedStatesObj);
    usedStates.sort();
    const usedTimezones = document.getElementById('grouper').value === 'tz'
        ? Object.keys(timezones)
            .filter( (timezone) => universities.includes(timezone)
                || ( timezone === 'Unknown' && universities.includes('') ) )
        : Object.entries(timezones)
            .filter( ([timezone, states]) => states.some( (state) => usedStates.includes(state) ) )
            .map( ([timezone, states]) => timezone );
    document.getElementById('filterTimezone').replaceChildren(...usedTimezones.map( (timezone) => {
        const option = document.createElement('option');
        option.setAttribute('value', 'tz-'+timezone);
        option.textContent = timezone;
        return option;
    }));
    document.getElementById('filterState').replaceChildren(...usedStates.map( (state) => {
        const option = document.createElement('option');
        option.setAttribute('value', state);
        option.textContent = state;
        return option;
    }));
}

/** Is this university the result of a user search
 *  @param {string[]} uni The university in question
 *  @return {boolean} */
function passesUserFilter([uni]) {
    const filter = document.getElementById('filter').value;
    if ( filter === 'all' ) {
        return true;
    }
    const onlyStates = filter.startsWith('tz-') ? timezones[filter.slice(3)] : [filter];
    if ( document.getElementById('grouper').value === 'state' ) {
        return onlyStates.includes(uni);
    }
    return onlyStates.some( (state) => unisInState[state].includes(uni) );
}

/** @param {string} contents */
function scatterPlotFile(contents) {
    // row: [Team, Games, Rate, Reseed]
    const xIndex = document.getElementById('x').value;
    const yIndex = document.getElementById('y').value;
    const data = contents.split('\n').slice(1).filter(getStringLength).map( (line) => line.split(',') )
        .filter(rowNonTrivial).filter(passesUserFilter);
    let xMin = Math.min(...data.map( (row) => +row[xIndex] ));
    let xMax = Math.max(...data.map( (row) => +row[xIndex] ));
    let yMin = Math.min(...data.map( (row) => +row[yIndex] ));
    let yMax = Math.max(...data.map( (row) => +row[yIndex] ));
    xMin *= xMin < 0 ? 1.1 : .9;
    yMin *= yMin < 0 ? 1.1 : .9;
    xMax *= xMax < 0 ? .9 : 1.1;
    yMax *= yMax < 0 ? .9 : 1.1;
    const xIsLog = 1 <= xMin && 10*xMin < xMax;
    const yIsLog = 1 <= yMin && 10*yMin < yMax;
    const svg = document.getElementsByTagName('svg')[0];
    const height = parseDecimal(svg.getAttribute('height'));
    const width = parseDecimal(svg.getAttribute('width'));
    createScatterFrame([xMin, xMax], xIsLog, [yMin, yMax], yIsLog);
    const teamList = document.getElementById('teamList');
    teamList.replaceChildren();
    data.forEach( (row, index) => {
        teamList.append(setElementAttributes(document.createElement('option'), {'value': row[0]}));
        const xDatum = +row[xIndex];
        const yDatum = +row[yIndex];
        const group = document.createElementNS(svgNamespace, 'g');
        const title = document.createElementNS(svgNamespace, 'title');
        const textContent = (row[0] || 'Unknown')
            + ' (' + fixFloatingPoint(xDatum.toFixed(2)) + ', '+fixFloatingPoint(yDatum.toFixed(2)) + ')';
        title.textContent = textContent;
        group.append(
            title,
            setElementAttributesNS(document.createElementNS(svgNamespace, 'circle'), {
                'cx': getPoint(xMin, xDatum, xMax, xIsLog)*width, 'stroke': 'black', 'r': 2, 'stroke-width': 1,
                'cy': (1-getPoint(yMin, yDatum, yMax, yIsLog))*height, 'fill': 'black', 'title': textContent,
            }),
        );
        svg.append(group);
    });
}

/** @param {number[]} xLoc
 *  @param {boolean} xIsLog
 *  @param {number[]} yLoc
 *  @param {boolean} yIsLog */
function createScatterFrame(xLoc, xIsLog, yLoc, yIsLog) {
    const [xMin, xMax] = xLoc;
    const [yMin, yMax] = yLoc;
    const svg = document.getElementsByTagName('svg')[0];
    const height = parseDecimal(svg.getAttribute('height'));
    const width = parseDecimal(svg.getAttribute('width'));
    const x0 = xMin * xMax > 0 || xIsLog ? 0 : getPoint(xMin, 0, xMax, false);
    const y0 = yMin * yMax > 0 || yIsLog ? 0 : getPoint(yMin, 0, yMax, false);
    const yAxis = setElementAttributesNS(document.createElementNS(svgNamespace, 'line'), {
        'x1': x0*width, 'y1': 0, 'x2': x0*width, 'y2': height, 'stroke': 'black', 'stroke-width': 1,
    });
    const xAxis = setElementAttributesNS(document.createElementNS(svgNamespace, 'line'), {
        'x1': 0, 'y1': (1-y0)*height, 'x2': width, 'y2': (1-y0)*height, 'stroke': 'black', 'stroke-width': 1,
    });
    const xTickLocations = getTickLocations(xMin, xMax, xIsLog);
    const xTicks = xTickLocations.map( (loc) => setElementAttributesNS(document.createElementNS(svgNamespace, 'line'), {
        'x1': getPoint(xMin, loc, xMax, xIsLog)*width, 'y1': (1-y0-1/20)*height, 'stroke-width': 1,
        'x2': getPoint(xMin, loc, xMax, xIsLog)*width, 'y2': (1-y0+1/20)*height, 'stroke': 'black',
    }));
    const xLabels = xTickLocations.map( (loc) => {
        const text = setElementAttributesNS(document.createElementNS(svgNamespace, 'text'), {
            'x': getPoint(xMin, loc, xMax, xIsLog)*width, 'y': (1-y0 + (y0?1:-1)/20)*height,
            'text-anchor': 'middle', 'dominant-baseline': ( y0? 'hanging' : 'alphabetic' ),
        });
        text.textContent = fixFloatingPoint(loc);
        return text;
    });
    const yTickLocations = getTickLocations(yMin, yMax, yIsLog);
    const yTicks = yTickLocations.map( (loc) => setElementAttributesNS(document.createElementNS(svgNamespace, 'line'), {
        'x1': (x0-1/20)*width, 'y1': (1-getPoint(yMin, loc, yMax, yIsLog))*height, 'stroke-width': 1,
        'x2': (x0+1/20)*width, 'y2': (1-getPoint(yMin, loc, yMax, yIsLog))*height, 'stroke': 'black',
    }));
    const yLabels = yTickLocations.map( (loc) => {
        const text = setElementAttributesNS(document.createElementNS(svgNamespace, 'text'), {
            'x': (x0+1/20)*width, 'y': (1-getPoint(yMin, loc, yMax, yIsLog))*height,
            'text-anchor': 'start', 'dominant-baseline': 'middle',
        });
        text.textContent = fixFloatingPoint(loc);
        return text;
    });
    svg.replaceChildren(xAxis, yAxis, ...xTicks, ...xLabels, ...yTicks, ...yLabels);
}

/** @param {number} min
 *  @param {number} max
 *  @param {boolean} isLog
 *  @return {float[]} */
function getTickLocations(min, max, isLog) {
    if ( isLog ) { // using a logarithmic scale
        const tickScale = Math.pow(10, Math.floor(Math.log10(max)));
        const ticks = [tickScale/10, tickScale*3/10, tickScale, tickScale*3].filter( (tick) => tick <= max );
        if ( ticks.length > 3 ) {
            ticks.shift();
        }
        return ticks;
    }
    const absMax = Math.max(-min, max);
    const tickScale = Math.pow(10, Math.floor(Math.log10(absMax)));
    const maxTick = Array(5).fill().map( (_, i) => 2*i*tickScale ).filter( (tick) => tick <= absMax ).pop()
        || tickScale;
    return Array(5).fill().map( (_, i) => (i-2)*maxTick/2 ).filter( (tick) => min <= tick && tick <= max );
}

/** @param {string} contents */
function plotWinLossFile(contents) {
    const spreadX = document.getElementById('individuate').checked;
    createWinLossFrame();
    const winLossMatrix = contents.split('\n').map( (line) => line.split(',').map(parseDecimal) );
    const maxRowSeed = winLossMatrix.findLastIndex( (row) => row.reduce( (a, b) => a+b ) );
    const maxColSeed = winLossMatrix[0].findLastIndex( (_, index) => colSum(winLossMatrix, index) );
    const maxSeed = Math.max(16, maxRowSeed, maxColSeed);
    const successCounter = Array(maxSeed+1);
    const totalCounter = Array(maxSeed+1);
    for ( let diff = 1; diff < maxSeed; diff++ ) {
        let total = 0;
        let successes = 0;
        let plotted = 0;
        for ( let row = 1; row < 17-diff; row++ ) {
            const innerTotal = winLossMatrix[row][row+diff] + winLossMatrix[row+diff][row];
            const innerSuccesses = winLossMatrix[row][row+diff];
            if ( innerTotal > 10 && spreadX ) {
                plotConfidenceInterval((diff+plotted/32)/maxSeed, getConfidenceInterval(innerSuccesses, innerTotal));
                plotted++;
            }
            total += innerTotal;
            successes += innerSuccesses;
        }
        successCounter[diff] = successes;
        totalCounter[diff] = total;
        if ( total > 10 && ! spreadX ) {
            plotConfidenceInterval(diff/maxSeed, getConfidenceInterval(successes, total));
        }
    }
    plotSigmoid(getLogisticBestFitRate(successCounter, totalCounter), maxSeed);
}

/** Determine which tournaments appear within a group
 *  @this XMLHttpRequest */
function getTournaments() {
    const group = this.responseURL.split('/').slice(-2)[0];
    const tournaments = this.responseText.split('\n').slice(1, -1).map( (line) => line.split(',')[0] );
    tournaments.sort();
    tournamentsOfGroup[group] = tournaments;
    listTournaments(group);
}

/** Constructs a win/loss plot of the given contents
 *  @param {string?} contents The contents to plot
 *  @this XMLHttpRequest */
function winLossPlotter(contents) {
    if ( typeof contents === 'string' ) {
        plotWinLossFile(contents);
    } else {
        contentsOfFile[this.responseURL.slice(document.location.href.length)] = this.responseText;
        plotWinLossFile(this.responseText);
    }
}

/** Constructs a scatter plot of the given contents
 *  @param {string?} contents The contents to plot
 *  @this XMLHttpRequest */
function scatterPlotter(contents) {
    if ( typeof contents === 'string' ) {
        scatterPlotFile(contents);
    } else {
        contentsOfFile[this.responseURL.slice(document.location.href.length)] = this.responseText;
        scatterPlotFile(this.responseText);
    }
    searchChange();
}

/** Records which universities are in which state
 *  @this XMLHttpRequest */
function putUnisInState() {
    this.responseText.split('\n').slice(1).forEach( (line) => {
        const row = line.split(',');
        const state = row[1] || 'Unknown';
        unisInState[state].push(row[0]);
    });
}

/** Do something with the contents of a file.  If we haven't loaded the file before, then we construct an
 *  XMLHttpRequest.  Otherwise, we use the contents as found in contentsOfFile.
 *  @param {string} file The file to load
 *  @param {function} processor What to do with the file's contents */
function processFile(file, processor) {
    if ( file in contentsOfFile ) {
        processor(contentsOfFile[file]);
    } else {
        const xhttp = new XMLHttpRequest();
        xhttp.addEventListener('load', processor);
        xhttp.open('GET', file);
        xhttp.send();
    }
}

/** Draw the axes for a win loss plot */
function createWinLossFrame() {
    const svg = document.getElementsByTagName('svg')[0];
    const height = parseDecimal(svg.getAttribute('height'));
    const width = parseDecimal(svg.getAttribute('width'));
    const halfWayPoint = setElementAttributesNS(document.createElementNS(svgNamespace, 'circle'), {
        'cx': 0, 'cy': height/2, 'r': 3, 'stroke': 'black', 'fill': 'black', 'stroke-width': 1,
    });
    const yAxis = setElementAttributesNS(document.createElementNS(svgNamespace, 'line'), {
        'x1': 0, 'y1': 0, 'x2': 0, 'y2': height, 'stroke': 'black', 'stroke-width': 2,
    });
    const xTop = setElementAttributesNS(document.createElementNS(svgNamespace, 'line'), {
        'x1': 0, 'y1': 0, 'x2': width, 'y2': 0, 'stroke': 'black', 'stroke-width': 2,
    });
    const xBottom = setElementAttributesNS(document.createElementNS(svgNamespace, 'line'), {
        'x1': 0, 'y1': height, 'x2': width, 'y2': height, 'stroke': 'black', 'stroke-width': 2,
    });
    svg.replaceChildren(halfWayPoint, yAxis, xTop, xBottom);
}

/** Plots sigmoid( rate*x ) on [0,maxX]
 *  @param {float} rate
 *  @param {float} maxX */
function plotSigmoid(rate, maxX) {
    const reseed = 0;
    const svg = document.getElementsByTagName('svg')[0];
    const height = parseDecimal(svg.getAttribute('height'));
    const width = parseDecimal(svg.getAttribute('width'));
    let lastX = 0;
    let lastY = sigmoid(rate*(lastX-reseed));
    let lastSlope = rate*derivSigmoid(rate*(lastX-reseed));
    let pathD = 'M0 '+height*(1-lastY);
    while ( lastX < maxX ) {
        const nextX = lastX+1;
        const nextY = sigmoid(rate*(nextX-reseed));
        const nextSlope = rate*derivSigmoid(rate*(nextX-reseed));
        const [midX, midY] = constrainedIntersection([lastX, lastY], lastSlope, [nextX, nextY], nextSlope);
        pathD += ' Q '+width*midX/maxX+' '+height*(1-midY)+' '+width*nextX/maxX+' '+height*(1-nextY);
        lastX = nextX;
        lastY = nextY;
        lastSlope = nextSlope;
    }
    svg.append(setElementAttributesNS(document.createElementNS(svgNamespace, 'path'), {
        'd': pathD, 'stroke': 'black', 'fill': 'transparent',
    }));
}

/** Finds a symmetric logistic best fit.  This is close to the method used by
 *  sklearn, but different in some way I haven't figured out.
 *  @param {int[]} successCounter The number of successes at seed differential [index]
 *  @param {int[]} totalCounter The number of attempts at seed differential [index]
 *  @return {float} */
function getLogisticBestFitRate(successCounter, totalCounter) {
    let rate = 0.5;
    const reseed = 0;
    const epochs = 1000;
    const learningRate = 0.2;
    const totalTotal = totalCounter.reduce( (a, b) => a+b );
    for ( let i = 0; i < epochs; i++ ) {
        rate += learningRate*totalCounter.reduce( (derivTotal, total, index) => {
            const successes = successCounter[index];
            const fails = total - successes;
            const prediction = sigmoid( rate*(index-reseed) );
            const deriv = successes*(1-prediction) - fails*prediction;
            return derivTotal + deriv*index;
        }, -rate*rate) / totalTotal;
    }
    return rate;
}

/** @param {float} xFrac [0,1]
 *  @param {{center: float, halfWidth: float}} confidenceInterval for a binomial random variable */
function plotConfidenceInterval(xFrac, confidenceInterval) {
    const svg = document.getElementsByTagName('svg')[0];
    const height = parseDecimal(svg.getAttribute('height'));
    const width = parseDecimal(svg.getAttribute('width'));
    const {center, halfWidth} = confidenceInterval;
    svg.append(setElementAttributesNS(document.createElementNS(svgNamespace, 'line'), {
        'x1': xFrac*width, 'y1': (1-center+halfWidth)*height, 'stroke': 'black',
        'x2': xFrac*width, 'y2': (1-center-halfWidth)*height, 'stroke-width': 2,
    }));
}

/** Find the intersection of a line through point1 with slope1 and through point2 with slope2.
 *  If the intersection would be outside the x-intervals, then clip it to occur
 *  at the boundary.  (If the slopes are parallel, the intersection is the midpoint of the two points.)
 *  @param {float[]} lastPoint
 *  @param {float} lastSlope
 *  @param {float[]} nextPoint
 *  @param {float} nextSlope
 *  @return {float[]} The intersection */
function constrainedIntersection(lastPoint, lastSlope, nextPoint, nextSlope) {
    const [lastX, lastY] = lastPoint;
    const [nextX, nextY] = nextPoint;
    /* (y-ly) = ls(x-lx)  =>  y = ly+ls(x-lx);  (y-ny) = ns(x-nx)  =>  y = ny+ns(x-nx)
     * ly+ls(x-lx) = ny+ns(x-nx)  =  ly+ls*x-ls*lx = ny+ns*x-ns*nx
     * ly-ny-ls*lx+ns*nx = ns*x-ls*x
     * x = ( ly-ny-ls*lx+ns*nx ) / (ns-ls)
     * y = ly+ls( ( ly-ny-ls*lx+ns*nx ) / (ns-ls) - lx )
     *   = ly+ls( ( ly-ny-ls*lx+ns*nx ) / (ns-ls) - ( lx*ns - lx*ls ) / (ns-ls) )
     *   = ly+ls( ( ly - ny - ls*lx + ns*nx - lx*ns + lx*ls ) / ( ns-ls ) )
     *   = ly+ls( ( ly - ny + ns*nx - lx*ns ) / ( ns-ls ) )
     *   = ( ly*ns - ly*ls + ls( ly - ny + ns*nx - lx*ns ) ) / ( ns-ls )
     *   = ( ly*ns - ly*ls + ls*ly - ls*ny + ls*ns*nx - ls*lx*ns ) ) / ( ns-ls )
     *   = ( ly*ns - ls*ny + ls*ns*nx - ls*lx*ns ) ) / ( ns-ls ) = ( ly*ns - ls*ny + ls*ns*(nx-lx) ) ) / ( ns-ls )
    */
    if ( nextSlope === lastSlope ) {
        return [(lastX+nextX)/2, (lastY+nextY)/2];
    }
    const x = ( lastY - nextY - lastSlope*lastX + nextSlope*nextX ) / ( nextSlope - lastSlope );
    const y = ( lastY*nextSlope - lastSlope*nextY + lastSlope*nextSlope*(nextX-lastX) ) / ( nextSlope - lastSlope );
    if ( x < lastX ) {
        return [lastX, lastY];
    }
    if ( nextX < x ) {
        return [nextX, nextY];
    }
    return [x, y];
}

/** Determine a Wilson 95% confidence interval, see Brown reference
 *  @param {int} successes
 *  @param {int} total
 *  @return {{center: float, halfWidth: float}} for a binomial random variable */
function getConfidenceInterval(successes, total) {
    const kappa = 1.96; // standard deviations to get 95% confidence
    const kappaSq = kappa*kappa;
    const pHat = successes / total;
    const qHat = (total - successes) / total;
    const center = (successes + kappaSq / 2) / (total + kappaSq);
    const halfWidth = kappa * total ** .5 * (pHat * qHat + kappaSq / (4 * total)) ** .5 / (total + kappaSq);
    return {center, halfWidth};
}

/** @param {number} number
 *  @return {string} The input, but dropping excess floating point digits at the end */
function fixFloatingPoint(number) {
    return number.toString()
        .replace(/(?<=\.\d*[1-9])0{5,}[1-9]$/, '')
        .replace(/(?<=\.\d*)([0-8])9{5,}\d$/, (d) => parseDecimal(d)+1)
        .replace(/\.0*$/, '');
}

/** @param {string[]} row
 *  @return {boolean} */
function rowNonTrivial(row) {
    return -16 < +row[3] && +row[3] < 16 && 0.01 < +row[2];
}

/** @param {number} min
 *  @param {number} data
 *  @param {number} max
 *  @param {boolean} isLog
 *  @return {number} The fraction of the way data is along the interval [min, max] */
function getPoint(min, data, max, isLog) {
    if ( isLog ) {
        return Math.log(data/min)/Math.log(max/min);
    } else {
        return (data-min)/(max-min);
    }
}

/** @param {Array.<Array.<int>>} matrix
 *  @param {int} col
 *  @return {int} The total of matrix along that particular column */
function colSum(matrix, col) {
    return matrix.reduce( (acc, row) => acc+row[col], 0 );
}

/** @param {HTMLElement} widget
 *  @param {boolean} shouldEnable */
function toggleWidget(widget, shouldEnable) {
    if ( shouldEnable ) {
        widget.removeAttribute('disabled');
    } else {
        widget.setAttribute('disabled', 'disabled');
    }
}

/** Set several attributes on a particular element with the null namespace. Chainable.
 *  @param {HTMLElement} element
 *  @param {Object} attributeObj
 *  @return {HTMLElement} The element, so this method can be chained */
function setElementAttributesNS(element, attributeObj) {
    Object.entries(attributeObj).forEach( (entry) => element.setAttributeNS(null, ...entry) );
    return element;
}

/** Set several attributes on a particular element. Chainable.
 *  @param {HTMLElement} element
 *  @param {Object} attributeObj
 *  @return {HTMLElement} The element, so this method can be chained */
function setElementAttributes(element, attributeObj) {
    Object.entries(attributeObj).forEach( (entry) => element.setAttribute(...entry) );
    return element;
}

/** @param {float} x
 *  @return {float} 1/(1+Math.exp(-x)) */
function sigmoid(x) {
    return 1/(1+Math.exp(-x));
}

/** @param {float} x
 *  @return {float} The derivative of the sigmoid function */
function derivSigmoid(x) {
    return Math.exp(-x)*sigmoid(x)*sigmoid(x);
}

/** @param {string} line
 *  @return {number} */
function getStringLength(line) {
    return line.length;
}

/** @param {string} input
    @return {Number} */
function parseDecimal(input) {
    return parseInt(input, 10);
}

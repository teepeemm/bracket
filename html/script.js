
'use strict';

const svgNamespace = 'http://www.w3.org/2000/svg',
    timezones = {
        'Eastern': ['Connecticut', 'District of Columbia', 'Delaware', 'Florida', 'Georgia', 'Indiana', 'Kentucky',
            'Maine', 'Maryland', 'Massachusetts', 'Michigan', 'New Hampshire', 'New Jersey', 'New York',
            'North Carolina', 'Ohio', 'Ontario', 'Pennsylvania', 'Quebec', 'Rhode Island', 'South Carolina',
            'Tennessee', 'Virginia', 'Vermont', 'West Virginia'],
        'Central': ['Alabama', 'Arkansas', 'Iowa', 'Illinois', 'Kansas', 'Louisiana', 'Manitoba', 'Minnesota',
            'Missouri', 'Mississippi', 'North Dakota', 'Nebraska', 'Oklahoma', 'South Dakota', 'Texas', 'Wisconsin'],
        'Saskatchewan': ['Saskatchewan'], // CST
        'Mountain': ['Alberta', 'Colorado', 'Idaho', 'Montana', 'New Mexico', 'Utah', 'Wyoming'],
        'Arizona': ['Arizona'], // MST
        'Pacific': ['California', 'Nevada', 'Oregon', 'Washington', 'British Columbia'],
        'Alaska': ['Alaska'],
        'Hawaii': ['Hawaii'],
        'Unknown': ['Unknown'],
    },
    tournamentsOfGroup = {},
    contentsOfFile = {},
    unisInState = {},
    labelWidth = 15;

Object.values(timezones).forEach( (arr) => {
    arr.forEach( (state) => {
        unisInState[state] = []
    })
});

processFile('state.csv', putUnisInState);
processFile('professional/state.csv', putUnisInState);

document.addEventListener('DOMContentLoaded', getQuery);

/** Use the search portion of the url to set the values of the widgets. Only happens onload. */
function getQuery() {
    const searchParams = new URLSearchParams(document.location.search);
    setFileToPlot(searchParams.get('file') || '');
    if ( searchParams.has('x') ) {
        document.getElementById('x').value = searchParams.get('x');
    }
    if ( searchParams.has('y') ) {
        document.getElementById('y').value = searchParams.get('y');
    }
    axesChange();
    if ( searchParams.get('individuate') === 'true' ) {
        document.getElementById('individuate').checked = true;
    }
    if ( searchParams.has('search') ) {
        document.getElementById('search').value = searchParams.get('search');
    }
    replot();
    addChangeListeners();
}

/** Runs after the search query has been loaded. */
function addChangeListeners() {
    ['individuate', 'filter'].forEach( (id) => document.getElementById(id).addEventListener('change', replot) );
    ['x', 'y'].forEach( (id) => document.getElementById(id).addEventListener('change', axesChange) );
    document.getElementById('graph').addEventListener('change', graphChange);
    document.getElementById('group').addEventListener('change', groupChange);
    document.getElementById('grouper').addEventListener('change', grouperChange);
    document.getElementById('search').addEventListener('change', searchChange);
    document.getElementById('tournament').addEventListener('change', tournamentChange);
}

/** Use the state of the widgets to construct the search portion of the url, so that {@link getQuery}() will get
 *  back to this state. */
function setQuery() {
    let query
        = `file=${getFileToPlot()}&x=${document.getElementById('x').value}&y=${document.getElementById('y').value}`;
    if ( document.getElementById('individuate').checked ) {
        query += '&individuate=true';
    }
    if ( document.getElementById('search').value ) {
        query += `&search=${document.getElementById('search').value}`;
    }
    window.history.pushState(null, '', `./?${query}`);
}

/** @return {string} What file should be used, according to the current settings */
function getFileToPlot() {
    let file = '';
    const group = document.getElementById('group').value,
        graph = document.getElementById('graph').value;
    if ( group !== 'all' ) {
        file = `${group}/`;
        const tourney = document.getElementById('tournament').value;
        if ( tourney !== 'all' ) {
            file += `${tourney}_`;
        }
    }
    if ( graph === 'seed_v_fraction' ) {
        file += 'winloss.csv';
    } else if ( graph === 'tourneyData' ) {
        file += 'group_betas.csv';
    } else {
        const grouper = document.getElementById('grouper').value;
        if ( grouper !== 'none' ) {
            file += `${grouper}_`;
        }
        file += 'reseed.csv';
    }
    return file;
}

/** The inverse operation of {@link getFileToPlot}().  Sets the widgets according to the input (which came from the
 *  url's search query string).
 *  @param {string} file */
function setFileToPlot(fileIn) {
    let file = fileIn,
        group = '',
        graph = '',
        grouper = '';
    if ( file.includes('/') ) {
        [group, file] = file.split('/', 2);
        document.getElementById('group').value = group;
        groupChange();
    }
    if ( file.endsWith('winloss.csv') || ! file ) {
        graph = 'seed_v_fraction';
        file = file.slice(0, -'winloss.csv'.length);
    } else if ( file.endsWith('group_betas.csv') ) {
        graph = 'tourneyData';
        file = file.slice(0, -'group_betas.csv'.length);
    } else if ( file.endsWith('reseed.csv') ) {
        graph = 'x_v_y';
        file = file.slice(0, -'reseed.csv'.length);
        ['conf', 'state', 'tz'].forEach( (option) => {
            if ( file.endsWith(`${option}_`) ) {
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
    if ( graph === 'x_v_y' && grouper ) {
        document.getElementById('grouper').value = grouper;
        grouperChange();
    }
}

/** Redraw the graph */
function replot() {
    const file = getFileToPlot(),
        graph = document.getElementById('graph').value,
        plotter = graph === 'seed_v_fraction' ? winLossPlotter : scatterPlotter;
    processFile(file, plotter);
    setQuery();
}

/** When the #group selector changes */
function groupChange() {
    const group = document.getElementById('group').value,
        tourneySelector = document.getElementById('tournament');
    document.getElementById('grouper').value = 'none';
    toggleWidget(tourneySelector, group !== 'all');
    toggleWidget(document.querySelector('#graph option[value="tourneyData"]'), group !== 'all');
    toggleWidget(document.querySelector('#grouper [value="conf"]'), group !== 'all');
    tourneySelector.value = 'all';
    if ( group !== 'all' ) {
        if ( group in tournamentsOfGroup ) {
            listTournaments(group);
        } else {
            processFile(`${group}/group_betas.csv`, getTournaments);
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
    const tourney = document.getElementById('tournament').value,
        groupByTourney = document.querySelector('#grouper option[value="conf"]'),
        tourneyDataOption = document.querySelector('#graph option[value="tourneyData"]');
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
    Array.from(document.getElementsByClassName('graph')).forEach( (span) => {
        span.style.fontWeight = 'normal'
    });
    document.querySelector(`.graph.${graph}`).style.fontWeight = 'bold';
    document.getElementById('seed_v_fraction').style.display = 'none';
    document.getElementById('x_v_y').style.display = 'none';
    if ( graph === 'tourneyData' ) {
        document.getElementById('x').value = 1;
        document.getElementById('y').value = 2;
    } else {
        document.getElementById(graph).style.display = 'block';
    }
    maybeUpdateFilters();
    axesChange();
}

/** When the #x or #y selectors change. */
function axesChange() {
    const graph = document.getElementById('graph').value;
    Array.from(document.getElementsByClassName('x_or_y')).forEach( (dt) => {
        dt.style.fontWeight = 'normal'
    });
    if ( graph !== 'seed_v_fraction' ) {
        document.getElementsByClassName('x_or_y')[document.getElementById('x').value-1].style.fontWeight = 'bold';
        document.getElementsByClassName('x_or_y')[document.getElementById('y').value-1].style.fontWeight = 'bold';
    }
    Array.from(document.getElementsByClassName('logScaled')).forEach( (span) => {
        span.style.display = 'none'
    });
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
        setElementAttributesNS(circle, {'fill': 'black', 'stroke': 'black', 'r': 2}),
    );
    if ( search.value.length < 4 ) {
        return;
    }
    setElementAttributesNS(document.querySelector(`svg circle[title="${search.value}"]`),
        {'stroke': 'red', 'fill': 'red', 'r': 3});
}

/** Wait until the universities have loaded, and then {@link updateFiltersUsing}(string[]) */
function maybeUpdateFilters() {
    const graph = document.getElementById('graph').value,
        file = getFileToPlot();
    if ( graph !== 'x_v_y' ) {
        return;
    }
    if ( file in contentsOfFile ) {
        updateFiltersUsing(contentsOfFile[file].split('\n').slice(1).filter(getStringLength)
            .map( (line) => line.split(',') ).filter(rowNonTrivial).map( (row) => row[0] ));
    } else {
        setTimeout(maybeUpdateFilters, 100);
    }
}

/** @param {string[]} universities */
function updateFiltersUsing(universities) {
    const graph = document.getElementById('graph').value,
        usedStatesObj = {};
    if ( graph !== 'x_v_y' ) {
        return;
    }
    if ( document.getElementById('grouper').value === 'state' ) {
        universities.forEach( (state) => {
            usedStatesObj[state || 'Unknown'] = 1
        });
    } else if ( document.getElementById('grouper').value === 'none' ) {
        universities.forEach( (university) => {
            const stateUni = Object.entries(unisInState).find( (entry) => entry[1].includes(university) )
                || ['Unknown'],
                [state] = stateUni;
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
            .filter( (entry) => entry[1].some( (state) => usedStates.includes(state) ) )
            .map( ([timezone]) => timezone );
    document.getElementById('filterTimezone').replaceChildren(...usedTimezones.map( (timezone) => {
        const option = document.createElement('option');
        option.setAttribute('value', `tz-${timezone}`);
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
    const filter = document.getElementById('filter').value,
        onlyStates = filter.startsWith('tz-') ? timezones[filter.slice(3)] : [filter];
    if ( filter === 'all' ) {
        return true;
    }
    if ( document.getElementById('grouper').value === 'state' ) {
        return onlyStates.includes(uni);
    }
    return onlyStates.some( (state) => unisInState[state].includes(uni) );
}

/** @param {string} contents */
function scatterPlotFile(contents) {
    // Row: [Team, Games, Rate, Reseed]
    const xIndex = document.getElementById('x').value,
        yIndex = document.getElementById('y').value,
        data = contents.split('\n').slice(1).filter(getStringLength).map( (line) => line.split(',') )
            .filter(rowNonTrivial).filter(passesUserFilter);
    let xMin = Math.min(...data.map( (row) => Number(row[xIndex]) )),
        xMax = Math.max(...data.map( (row) => Number(row[xIndex]) )),
        yMin = Math.min(...data.map( (row) => Number(row[yIndex]) )),
        yMax = Math.max(...data.map( (row) => Number(row[yIndex]) ));
    xMin *= xMin < 0 ? 1.1 : .9;
    yMin *= yMin < 0 ? 1.1 : .9;
    xMax *= xMax < 0 ? .9 : 1.1;
    yMax *= yMax < 0 ? .9 : 1.1;
    const xIsLog = 1 <= xMin && 10*xMin < xMax,
        yIsLog = 1 <= yMin && 10*yMin < yMax,
        [svg] = document.getElementsByTagName('svg'),
        height = parseDecimal(svg.getAttribute('height'))-labelWidth,
        width = parseDecimal(svg.getAttribute('width'))-labelWidth,
        teamList = document.getElementById('teamList');
    if ( xIsLog ) {
        document.getElementsByClassName('logScaled')[document.getElementById('x').value-1].style.display = 'inline';
    }
    if ( yIsLog ) {
        document.getElementsByClassName('logScaled')[document.getElementById('y').value-1].style.display = 'inline';
    }
    createScatterFrame([xMin, xMax], xIsLog, [yMin, yMax], yIsLog);
    addAxesLabels(svg, height, width);
    teamList.replaceChildren();
    data.forEach( (row) => {
        teamList.append(setElementAttributes(document.createElement('option'), {'value': row[0]}));
        const xDatum = Number(row[xIndex]),
            yDatum = Number(row[yIndex]),
            group = document.createElementNS(svgNamespace, 'g'),
            title = document.createElementNS(svgNamespace, 'title'),
            xToShow = fixFloatingPoint(xDatum.toFixed(2)),
            yToShow = fixFloatingPoint(yDatum.toFixed(2)),
            textContent = `${row[0] || 'Unknown'} (${xToShow}, ${yToShow})`;
        title.textContent = textContent;
        group.append(
            title,
            setElementAttributesNS(document.createElementNS(svgNamespace, 'circle'), {
                'cx': getPoint(xMin, xDatum, xMax, xIsLog)*width+labelWidth, 'stroke': 'black', 'r': 2, 'stroke-width': 1,
                'cy': (1-getPoint(yMin, yDatum, yMax, yIsLog))*height, 'fill': 'black', 'title': textContent,
            }),
        );
        svg.append(group);
    });
}

/** @param {number[]} xRange
 *  @param {boolean} xIsLog
 *  @param {number[]} yRange
 *  @param {boolean} yIsLog */
function createScatterFrame(xRange, xIsLog, yRange, yIsLog) {
    const [xMin, xMax] = xRange,
        [yMin, yMax] = yRange,
        [svg] = document.getElementsByTagName('svg'),
        height = parseDecimal(svg.getAttribute('height'))-labelWidth,
        width = parseDecimal(svg.getAttribute('width'))-labelWidth,
        x0 = xMin * xMax > 0 || xIsLog ? 0 : getPoint(xMin, 0, xMax, false),
        y0 = yMin * yMax > 0 || yIsLog ? 0 : getPoint(yMin, 0, yMax, false),
        yAxis = setElementAttributesNS(document.createElementNS(svgNamespace, 'line'), {
            'x1': x0*width+labelWidth, 'y1': 0, 'x2': x0*width+labelWidth, 'y2': height, 'stroke': 'black', 'stroke-width': 1,
        }),
        xAxis = setElementAttributesNS(document.createElementNS(svgNamespace, 'line'), {
            'x1': labelWidth, 'y1': (1-y0)*height, 'x2': width+labelWidth, 'y2': (1-y0)*height, 'stroke': 'black', 'stroke-width': 1,
        }),
        xTickLocations = getTickLocations(xMin, xMax, xIsLog),
        xTicks = xTickLocations.map( (loc) => setElementAttributesNS(document.createElementNS(svgNamespace, 'line'), {
            'x1': getPoint(xMin, loc, xMax, xIsLog)*width+labelWidth, 'y1': (1-y0-1/50)*height, 'stroke-width': 1,
            'x2': getPoint(xMin, loc, xMax, xIsLog)*width+labelWidth, 'y2': (1-y0+1/50)*height, 'stroke': 'black',
        })),
        xTickLabels = xTickLocations.map( (loc) => {
            const text = setElementAttributesNS(document.createElementNS(svgNamespace, 'text'), {
                'x': getPoint(xMin, loc, xMax, xIsLog)*width+labelWidth, 'y': (1-y0 + (y0?1:-1)/50)*height,
                'text-anchor': 'middle', 'dominant-baseline': ( y0? 'hanging' : 'alphabetic' ),
            });
            text.textContent = fixFloatingPoint(loc);
            return text;
        }),
        yTickLocations = getTickLocations(yMin, yMax, yIsLog),
        yTicks = yTickLocations.map( (loc) => setElementAttributesNS(document.createElementNS(svgNamespace, 'line'), {
            'x1': (x0-1/50)*width+labelWidth, 'y1': (1-getPoint(yMin, loc, yMax, yIsLog))*height, 'stroke-width': 1,
            'x2': (x0+1/50)*width+labelWidth, 'y2': (1-getPoint(yMin, loc, yMax, yIsLog))*height, 'stroke': 'black',
        })),
        yTickLabels = yTickLocations.map( (loc) => {
            const text = setElementAttributesNS(document.createElementNS(svgNamespace, 'text'), {
                'x': (x0+1/40)*width+labelWidth, 'y': (1-getPoint(yMin, loc, yMax, yIsLog))*height,
                'text-anchor': 'start', 'dominant-baseline': 'middle',
            });
            text.textContent = fixFloatingPoint(loc);
            return text;
        });
    svg.replaceChildren(xAxis, yAxis, ...xTicks, ...xTickLabels, ...yTicks, ...yTickLabels);
}

function addAxesLabels(svg, height, width) {
    const graph = document.getElementById('graph').value;
    let xContent = document.getElementById('x').selectedOptions[0].textContent,
        yContent = document.getElementById('y').selectedOptions[0].textContent;
    if ( graph === 'seed_v_fraction' ) {
        xContent = 'Seed differential';
        yContent = 'Fraction won';
    }
    const xLabel = setElementAttributesNS(document.createElementNS(svgNamespace, 'text'), {
        'text-anchor': 'middle', 'x': width/2, 'y': height+10,
    });
    xLabel.textContent = xContent;
    svg.appendChild(xLabel);
    const yLabel = setElementAttributesNS(document.createElementNS(svgNamespace, 'text'), {
        'dominant-baseline': 'central', 'text-anchor': 'middle', 'transform': `rotate(-90, 5, ${height/2})`, 'x': 5, 'y': height/2,
    });
    yLabel.textContent = yContent;
    svg.appendChild(yLabel);
}

/** @param {number} min
 *  @param {number} max
 *  @param {boolean} isLog
 *  @return {float[]} */
function getTickLocations(min, max, isLog) {
    if ( isLog ) {
        const tickScale = 10**Math.floor(Math.log10(max)),
            ticks = [tickScale/10, tickScale*3/10, tickScale, tickScale*3].filter( (tick) => tick <= max );
        if ( ticks.length > 3 ) {
            ticks.shift();
        }
        return ticks;
    }
    const absMax = Math.max(-min, max),
        tickScale = 10**Math.floor(Math.log10(absMax)),
        maxTick = Array(5).fill().map( (_, i) => 2*i*tickScale ).filter( (tick) => tick <= absMax ).pop()
            || tickScale;
    return Array(5).fill().map( (_, i) => (i-2)*maxTick/2 ).filter( (tick) => min <= tick && tick <= max );
}

/** @param {string} contents */
function plotWinLossFile(contents) {
    createWinLossFrame();
    const spreadX = document.getElementById('individuate').checked,
        winLossMatrix = contents.split('\n').map( (line) => line.split(',').map(parseDecimal) ),
        maxRowSeed = winLossMatrix.findLastIndex( (row) => row.reduce( (a, b) => a+b ) ),
        maxColSeed = winLossMatrix[0].findLastIndex( (_, index) => colSum(winLossMatrix, index) ),
        maxSeed = Math.max(16, maxRowSeed, maxColSeed),
        successCounter = Array(maxSeed+1),
        totalCounter = Array(maxSeed+1);
    for ( let diff = 1; diff < maxSeed; diff += 1 ) {
        let total = 0,
            successes = 0,
            plotted = 0;
        for ( let row = 1; row < 17-diff; row += 1 ) {
            const innerTotal = winLossMatrix[row][row+diff] + winLossMatrix[row+diff][row],
                innerSuccesses = winLossMatrix[row][row+diff];
            if ( 10 < innerTotal && spreadX ) {
                plotConfidenceInterval((diff+plotted/32)/maxSeed, getConfidenceInterval(innerSuccesses, innerTotal));
                plotted += 1;
            }
            total += innerTotal;
            successes += innerSuccesses;
        }
        successCounter[diff] = successes;
        totalCounter[diff] = total;
        if ( ( 10 < total ) && ! spreadX ) {
            plotConfidenceInterval(diff/maxSeed, getConfidenceInterval(successes, total));
        }
    }
    plotSigmoid(getLogisticBestFitRate(successCounter, totalCounter), maxSeed);
}

/** Determine which tournaments appear within a group
 *  @this XMLHttpRequest */
function getTournaments() {
    const [group] = this.responseURL.split('/').slice(-2),
        tournaments = this.responseText.split('\n').slice(1, -1).map( (line) => line.split(',')[0] );
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
        const baseUrl = document.location.origin + document.location.pathname;
        contentsOfFile[this.responseURL.slice(baseUrl.length)] = this.responseText;
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
        const baseUrl = document.location.origin + document.location.pathname;
        contentsOfFile[this.responseURL.slice(baseUrl.length)] = this.responseText;
        scatterPlotFile(this.responseText);
    }
    searchChange();
}

/** Records which universities are in which state
 *  @this XMLHttpRequest */
function putUnisInState() {
    this.responseText.split('\n').slice(1).forEach( (line) => {
        const row = line.split(','),
            state = row[1] || 'Unknown';
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
    const [svg] = document.getElementsByTagName('svg'),
        height = parseDecimal(svg.getAttribute('height'))-labelWidth,
        width = parseDecimal(svg.getAttribute('width'))-labelWidth,
        halfWayPoint = setElementAttributesNS(document.createElementNS(svgNamespace, 'circle'), {
            'cx': labelWidth, 'cy': height/2, 'fill': 'black', 'r': 3, 'stroke': 'black', 'stroke-width': 1,
        }),
        yAxis = setElementAttributesNS(document.createElementNS(svgNamespace, 'line'), {
            'stroke': 'black', 'stroke-width': 1, 'x1': labelWidth, 'x2': labelWidth, 'y1': 0, 'y2': height,
        }),
        xTop = setElementAttributesNS(document.createElementNS(svgNamespace, 'line'), {
            'stroke': 'black', 'stroke-width': 1, 'x1': labelWidth, 'x2': width+labelWidth, 'y1': 0, 'y2': 0,
        }),
        xBottom = setElementAttributesNS(document.createElementNS(svgNamespace, 'line'), {
            'stroke': 'black', 'stroke-width': 1, 'x1': labelWidth, 'x2': width+labelWidth, 'y1': height, 'y2': height,
        });
    svg.replaceChildren(halfWayPoint, yAxis, xTop, xBottom);
    addAxesLabels(svg, height, width);
}

/** Plots sigmoid( rate*x ) on [0,maxX]
 *  @param {float} rate
 *  @param {float} maxX */
function plotSigmoid(rate, maxX) {
    const [svg] = document.getElementsByTagName('svg'),
        height = parseDecimal(svg.getAttribute('height'))-labelWidth,
        reseed = 0,
        width = parseDecimal(svg.getAttribute('width'))-labelWidth;
    let lastX = 0,
        lastSlope = rate*derivSigmoid(rate*(lastX-reseed)),
        lastY = sigmoid(rate*(lastX-reseed)),
        pathD = `M${labelWidth} ${height*(1-lastY)}`;
    while ( lastX < maxX ) {
        const nextX = lastX+1,
            nextY = sigmoid(rate*(nextX-reseed)),
            nextSlope = rate*derivSigmoid(rate*(nextX-reseed)),
            [midX, midY] = constrainedIntersection([lastX, lastY], lastSlope, [nextX, nextY], nextSlope);
        pathD += ` Q ${width*midX/maxX+labelWidth} ${height*(1-midY)} ${width*nextX/maxX+labelWidth} ${height*(1-nextY)}`;
        lastX = nextX;
        lastY = nextY;
        lastSlope = nextSlope;
    }
    svg.append(setElementAttributesNS(document.createElementNS(svgNamespace, 'path'), {
        'd': pathD, 'fill': 'transparent', 'stroke': 'black',
    }));
}

/** Finds a symmetric logistic best fit.  This is close to the method used by
 *  sklearn, but different in some way I haven't figured out.
 *  @param {int[]} successCounter The number of successes at seed differential [index]
 *  @param {int[]} totalCounter The number of attempts at seed differential [index]
 *  @return {float} */
function getLogisticBestFitRate(successCounter, totalCounter) {
    let rate = 0.5;
    const reseed = 0,
        epochs = 1000,
        learningRate = 0.2,
        totalTotal = totalCounter.reduce( (a, b) => a+b );
    for ( let i = 0; i < epochs; i += 1 ) {
        rate += learningRate*totalCounter.reduce( (derivTotal, total, index) => {
            const successes = successCounter[index],
                fails = total - successes,
                prediction = sigmoid( rate*(index-reseed) ),
                deriv = successes*(1-prediction) - fails*prediction;
            return derivTotal + deriv*index;
        }, -rate*rate) / totalTotal;
    }
    return rate;
}

/** @param {float} xFrac [0,1]
 *  @param {{center: float, halfWidth: float}} confidenceInterval for a binomial random variable */
function plotConfidenceInterval(xFrac, confidenceInterval) {
    const [svg] = document.getElementsByTagName('svg'),
        height = parseDecimal(svg.getAttribute('height'))-labelWidth,
        width = parseDecimal(svg.getAttribute('width'))-labelWidth,
        {center, halfWidth} = confidenceInterval;
    svg.append(setElementAttributesNS(document.createElementNS(svgNamespace, 'line'), {
        'x1': xFrac*width+labelWidth, 'y1': (1-center+halfWidth)*height, 'stroke-width': 2,
        'x2': xFrac*width+labelWidth, 'y2': (1-center-halfWidth)*height, 'stroke': 'black',
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
    const [lastX, lastY] = lastPoint,
        [nextX, nextY] = nextPoint;
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
    const x = ( lastY - nextY - lastSlope*lastX + nextSlope*nextX ) / ( nextSlope - lastSlope ),
        y = ( lastY*nextSlope - lastSlope*nextY + lastSlope*nextSlope*(nextX-lastX) ) / ( nextSlope - lastSlope );
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
    const kappa = 1.96, // Standard deviations to get 95% confidence
        kappaSq = kappa*kappa,
        pHat = successes / total,
        qHat = (total - successes) / total,
        center = (successes + kappaSq / 2) / (total + kappaSq),
        halfWidth = kappa * total ** .5 * (pHat * qHat + kappaSq / (4 * total)) ** .5 / (total + kappaSq);
    return {center, halfWidth};
}

/** @param {number} number
 *  @return {string} The input, but dropping excess floating point digits at the end */
function fixFloatingPoint(number) {
    return number.toString()
        .replace(/(?<=\.\d*[1-9])0{5,}[1-9]$/u, '')
        .replace(/(?<=\.\d*)(?<last>[0-8])9{5,}\d$/u, (...args) => parseDecimal(args.at(-1).last)+1)
        .replace(/\.0*$/u, '');
}

/** @param {string[]} row
 *  @return {boolean} */
function rowNonTrivial(row) {
    return ( -16 < Number(row[3]) ) && ( Number(row[3]) < 16 ) && ( 0.01 < Number(row[2]) );
}

/** @param {number} min
 *  @param {number} data
 *  @param {number} max
 *  @param {boolean} isLog
 *  @return {number} The fraction of the way data is along the interval [min, max] */
function getPoint(min, data, max, isLog) {
    if ( isLog ) {
        return Math.log(data/min)/Math.log(max/min);
    }
    return (data-min)/(max-min);
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

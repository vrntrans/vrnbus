(function () {
    'use strict';

    /**
     * Converts <code>value</code> to string and pad it with leading zeroes until resulting string reaches <code>length</code>
     * @param {Number} value
     * @param {Number} [length=2]
     * @return {String}
     */
    function leadingZeroes(value, length) {
        var str = value.toString(),
            finalLen = arguments.length == 2 ? length : 2;

        if (str.length > finalLen) {
            return str;
        }

        // this task can be accomplished in one line — empty for cycle
        for (str; str.length < finalLen; str = '0' + str);

        return str;
    }


    var tokens = {
        YYYY: function (date) {
            return date.getFullYear();
        },
        YY: function (date) {
            return leadingZeroes(date.getFullYear() % 100);
        },
        MM: function (date) {
            return leadingZeroes(date.getMonth() + 1);
        },
        M: function (date) {
            return date.getMonth() + 1;
        },
        dd: function (date) {
            return leadingZeroes(date.getDate());
        },
        d: function (date) {
            return date.getDate();
        },
        hh: function (date) {
            return leadingZeroes(date.getHours());
        },
        h: function (date) {
            return date.getHours();
        },
        mm: function (date) {
            return leadingZeroes(date.getMinutes());
        },
        m: function (date) {
            return date.getMinutes();
        },
        ss: function (date) {
            return leadingZeroes(date.getSeconds());
        },
        s: function (date) {
            return date.getSeconds();
        },
        ff: function (date) {
            return leadingZeroes(date.getMilliseconds(), 3);
        },
        f: function (date) {
            return date.getMilliseconds();
        },
        Z: function (date) {
            var tz = date.getTimezoneOffset(),
                hours = Math.abs(Math.floor(tz / 60)),
                mins = tz % 60,
                sign = tz > 0 ? '+' : '-';

            return [sign, leadingZeroes(hours), ':', leadingZeroes(mins)].join('');
        }
    };

    var possibleFormats = [];
    for (var extractor in tokens) {
        if (tokens.hasOwnProperty(extractor)) {
            possibleFormats.push(extractor)
        }
    }
    var regexp = new RegExp(possibleFormats.join('|'), 'mg');

    /**
     * Formats date according to <b>format</b> string.
     * Format string may consist of any characters, but some of them considered tokens,
     * and will be replaced by appropriate value from <b>date</b>.
     * Possible tokens include:
     *  <b>YYYY</b>: 4-digit year
     *  <b>YY</b>: last 2 digit of year
     *  <b>MM</b>: ISO8601-compatible number of month (i.e. zero-padded) in year (with January being 1st month)
     *  <b>M</b>: number of month in year without zero-padding (with January being 1st month)
     *  <b>dd</b>: zero-padded number of day in month
     *  <b>d</b>: number of day in month
     *  <b>hh</b>: zero-padded hour
     *  <b>h</b>: hour
     *  <b>mm</b>: zero-padded minutes
     *  <b>m</b>: minutes
     *  <b>ss</b>: zero-padded seconds
     *  <b>s</b>: seconds
     *  <b>ff</b>: zero-padded milliseconds
     *  <b>f</b>: milliseconds
     *  <b>TZ</b>: time-zone in ISO8601-compatible format (i.e. "-04:00")
     *
     *  Longer tokens take precedence over shorter ones (so "MM" will aways be "04", not "44" in april).
     *
     * @param {String} format
     * @param {Date|Number} [date=Date.now()]
     * @return {String}
     */
    function datef (format, date) {
        var dt = (arguments.length === 2 && date) ? date instanceof Date ? date : new Date(date) : new Date(),
            result = new String(format);

        return result.replace(regexp, function (match) {
            return tokens[match](dt);
        });
    };


    /**
     * Creates formatting function. Basically just curry over datef.
     * @return {Function} readied formatting function with one argument — date.
     */
    var createFormatter = datef.createFormatter = function (format) {
        return function (date) {
            return datef(format, date)
        }
    };

    /**
     * Predefined formatters storage.
     * @type {Object}
     */
    var formatters = datef.formatters = {};

    /**
     * Creates formatting function and files it under <code>datef.formatters[name]</code>
     * @param {String} name
     * @param {String} format
     * @return {Function} readied formatting function with one argument — date.
     */
    var register = datef.register = function (name, format) {
        return formatters[name] = createFormatter(format)
    };


    // Let's create some basic formats
    register('ISODate', 'YYYY-MM-dd');
    register('ISOTime', 'hh:mm:ss');
    register('ISODateTime', 'YYYY-MM-ddThh:mm:ss');
    register('ISODateTimeTZ', 'YYYY-MM-ddThh:mm:ssZ');


    // get reference to global object
    var root;
    if (typeof window !== 'undefined') { // we're in browser, captain!
        root = window
    } else if (typeof global !== 'undefined') { // node.js
        root = global;
    }
    else {
        root = this;
    }

    // conflict management — save link to previous content of datef, whatever it was.
    var prevDatef = root.datef;

    /**
     * Cleans global namespace, restoring previous value of window.datef, and returns datef itself.
     * @return {datef}
     */
    datef.noConflict = function () {
        root.datef = prevDatef;
        return this;
    };

    // Expose our precious function to outer world.
    if (typeof exports !== 'undefined') { // node.js way
        module.exports.datef = datef;
    } else if (typeof define === 'function' && define.amd) { // requirejs/amd env
        define(
            'datef',
            [],
            function () {
                return datef;
            }
        );
    } else { // plain browser environment
        root.datef = datef;
    }
})();
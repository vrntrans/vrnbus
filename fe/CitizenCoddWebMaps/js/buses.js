var Car = (function () {
    "use strict";

    var directionsVariants = {
        classes: {
            16: ['w', 'sww', 'sw', 'ssw', 's', 'sse', 'se', 'see', 'e', 'nee', 'ne', 'nne', 'n', 'nnw', 'nw', 'nww'],
        },
        n: function (x,y,n) {
            n = n || 8;
            var n2 = n>>1; // half of n
            var number = (Math.floor(Math.atan2(x,y)/Math.PI*n2+1/n)+n2) % n; // seems like there is a little bug here
            return {n: number, t: directionsVariants.classes[n][ number ]};
        },
        16: function (x,y) { // -> values in range [0, 16]
            return directionsVariants.n(x,y,16);
        }
    };

    /**
     * Класс машинки.
     * @class
     * @name Car
     * @param {Object} [options]
     */
    var Car = function (options) {
        var properties = {
            geometry: {
                type: "Point"
            }
        };
        options = options || {};
        options.preset = options.preset || 'twirl#greenStretchyIcon';
        var result = new ymaps.GeoObject(properties, options);

        return result
    };

    return Car;})
()
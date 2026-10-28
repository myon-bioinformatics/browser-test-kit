"use strict";
// Preserve both the original require() API and CLI exit status.
const btk = require("./btk.cjs");
module.exports = btk;
if (require.main === module) process.exit(btk.main(process.argv.slice(2)));

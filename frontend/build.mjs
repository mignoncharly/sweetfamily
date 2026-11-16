import {copyFileSync,mkdirSync} from "node:fs";
mkdirSync("dist",{recursive:true});
copyFileSync("src/main.css","dist/main.css");

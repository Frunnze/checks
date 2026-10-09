const fs = require("fs");

const acceptedAdvisories = process.argv.slice(2);
const auditReport = JSON.parse(fs.readFileSync(0, "utf8"));
const unaccepted = new Set();

for (const vulnerability of Object.values(auditReport.vulnerabilities ?? {})) {
  for (const cause of vulnerability.via) {
    if (typeof cause !== "object") continue;

    const advisory = cause.url.split("/").pop();

    if (!acceptedAdvisories.includes(advisory)) {
      unaccepted.add(`${cause.name}: ${cause.url} (${cause.severity})`);
    }
  }
}

for (const finding of [...unaccepted].sort()) {
  process.stdout.write(finding + "\n");
}

const fs = require('fs');
try {
    const http = require('http');
    const server = http.createServer((req, res) => { res.end('ok'); });
    server.listen(3000);
    fs.writeFileSync('C:\\Users\\ibrah\\OneDrive\\Desktop\\Course Planner\\success.log', 'Started');
} catch(e) {
    fs.writeFileSync('C:\\Users\\ibrah\\OneDrive\\Desktop\\Course Planner\\error.log', e.toString());
}

"""SPA-aware development server.

Serves index.html for any path that doesn't match a real file,
enabling pushState-based client-side routing on localhost.
"""
import http.server
import os


class SPAHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        path = self.translate_path(self.path)
        if os.path.exists(path) and not os.path.isdir(path):
            super().do_GET()
        elif os.path.isdir(path) and os.path.exists(os.path.join(path, 'index.html')):
            super().do_GET()
        else:
            self.path = '/index.html'
            super().do_GET()


if __name__ == '__main__':
    server = http.server.HTTPServer(('', 3000), SPAHandler)
    print('SPA server running on http://localhost:3000')
    server.serve_forever()

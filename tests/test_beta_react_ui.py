"""React build integration: protected production UI and static assets."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import beta.server as server
from beta.backend import FileBackend
from fastapi.testclient import TestClient

class ReactUiTests(unittest.TestCase):
    def test_login_is_self_hosted_and_csp_compatible(self):
        with tempfile.TemporaryDirectory() as t:
            app=server.create_app(FileBackend(t,{}),
              password='password-longer-than-sixteen',
              session_secret='secret-longer-than-thirty-two-characters-012345')
            with TestClient(app,base_url='https://example.org') as client:
                page=client.get('/login')
                self.assertEqual(page.status_code,200)
                self.assertIn('href="/login.css"',page.text)
                self.assertIn('method="post"',page.text)
                self.assertNotIn('<script',page.text)
                styles=client.get('/login.css')
                self.assertEqual(styles.status_code,200)
                self.assertIn('text/css',styles.headers['content-type'])
                self.assertIn("style-src 'self'",page.headers['content-security-policy'])

    def test_fallback_without_build(self):
        with tempfile.TemporaryDirectory() as t:
            b=FileBackend(t,{})
            app=server.create_app(b,password='password-longer-than-sixteen',session_secret='secret-longer-than-thirty-two-characters-012345')
            with patch.object(server,'REACT_DIST',Path(t)/'missing'), TestClient(app,base_url='https://example.org') as client:
                client.post('/login',data={'password':'password-longer-than-sixteen'})
                r=client.get('/')
                self.assertEqual(r.status_code,200)
                self.assertIn('site.js',r.text)
    def test_react_assets_require_login_and_forbid_traversal(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/'react';(root/'assets').mkdir(parents=True)
            (root/'index.html').write_text('<!doctype html><script type="module" src="/ui/assets/app.js"></script>')
            (root/'assets'/'app.js').write_text('document.body.dataset.react="yes"')
            (root/'assets'/'app.css').write_text('body{background:white}')
            (Path(t)/'private.js').write_text('do-not-serve')
            b=FileBackend(Path(t)/'jobs',{})
            app=server.create_app(b,password='password-longer-than-sixteen',session_secret='secret-longer-than-thirty-two-characters-012345')
            with patch.object(server,'REACT_DIST',root), TestClient(app,base_url='https://example.org') as client:
                self.assertEqual(client.get('/ui/assets/app.js').status_code,401)
                self.assertEqual(client.get('/',follow_redirects=False).status_code,303)
                client.post('/login',data={'password':'password-longer-than-sixteen'})
                self.assertIn('/ui/assets/app.js',client.get('/').text)
                js=client.get('/ui/assets/app.js')
                self.assertEqual(js.status_code,200)
                self.assertIn('nosniff',js.headers.get('x-content-type-options',''))
                self.assertEqual(js.headers.get('cache-control'),'no-store, private')
                self.assertEqual(client.get('/ui/assets/app.css').status_code,200)
                self.assertEqual(client.get('/ui/other.js').status_code,404)
                self.assertEqual(client.get('/ui/assets/missing.js').status_code,404)
                self.assertEqual(client.get('/ui/assets/../private.js').status_code,404)

if __name__=='__main__':
    unittest.main()

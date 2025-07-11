<?php
require 'vendor/autoload.php';

$dotenv = Dotenv\Dotenv::createImmutable(__DIR__ . '/../../');
$dotenv->load();
$config = require 'config.php';

use GuzzleHttp\Client;
use GuzzleHttp\Cookie\CookieJar;

// Step 1: Create client with cookie support
$jar = new CookieJar();
$client = new Client([
    'base_uri' => 'https://pv.inteless.com',
        'cookies' => $jar
        ]);

        // Step 2: GET /login page to retrieve CSRF token from HTML
        $response = $client->get('/login');
        $html = (string)$response->getBody();
        file_put_contents('login_page.html', $html);
        echo "Wrote login HTML to login_page.html\n";
        $html = (string)$response->getBody();
        preg_match('/<meta name="_csrf" content="([^"]+)"/', $html, $matches);
        $csrfToken = $matches[1] ?? null;

        if (!$csrfToken) {
            echo "Failed to extract CSRF token.\n";
                exit(1);
                }

                // Step 3: POST to login API with credentials and CSRF token
                $response = $client->post('/api/v1/user/login', [
                    'headers' => [
                            'X-CSRF-TOKEN' => $csrfToken,
                                    'Referer' => 'https://pv.inteless.com/login',
                                            'Content-Type' => 'application/json'
                                                ],
                                                    'json' => [
                                                            'userName' => $config['email'],
                                                                    'password' => $config['password']
                                                                        ]
                                                                        ]);

                                                                        $data = json_decode($response->getBody(), true);
                                                                        $token = $data['data']['token'] ?? null;

                                                                        if (!$token) {
                                                                            echo "Login failed: no token returned.\n";
                                                                                exit(1);
                                                                                }

                                                                                echo "✅ Authenticated. Token: " . substr($token, 0, 10) . "...\n";
                                                                                
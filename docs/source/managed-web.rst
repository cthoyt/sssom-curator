##################
 Login with ORCiD
##################

The SSSOM Curator web application can integrate ORCiD as an authentication system via
:mod:`flask_dance`. When running the CLI, you can pass ``--live-login`` to enable this.

First, register a public API client with ORCiD following the steps in the `first-party
guide
<https://info.orcid.org/documentation/integration-guide/registering-a-public-api-client/>`_
to fill out the form on https://orcid.org/developer-tools.

***********************
 Storing Configuration
***********************

This will give you two important strings: a client identifier and a client secret. If
you're testing locally, put these in a file ``~/.config/sssom_curator.ini`` with the
following contents such that it can be automatically read with :mod:`pystow`.

.. code-block:: ini

    [sssom_curator]
    orcid_client_id = APP-XXXXXXXXXXXXXXXX
    orcid_client_secret = XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX

Alternatively, you can set the environment variables ``SSSOM_CURATOR_ORCID_CLIENT_ID``
and ``SSSOM_CURATOR_ORCID_CLIENT_SECRET``.

***********************
 Registering Redirects
***********************

The ORCiD authentication implementation from :mod:`flask_dance` mounts to the absolute
path ``/login/orcid/authorized`` in your app. For example, if you would like to test
login with ORCiD locally, then you can register a redirect in ORCiD's panel to
``https://127.0.0.1:8775/login/orcid/authorized``.

Note that ORCID doesn't allow using "localhost" as the host, so you have to use either
``127.0.0.1`` or ``0.0.0.0`` to make this work locally. In general, you can use any
resolvable host and port combination.

*********
 Proxies
*********

If you're running behind a proxy, then use ``--proxy-fix`` to enable

.. code-block:: python

    app = ProxyFix(
        app,
        x_for=1,  # get the real IP address of who makes the request
        x_proto=1,  # gets whether its http or https from the X-Forwarded header
        # the other ones are left as default
    )

********************
 Serving over HTTPS
********************

HTTPS is required for ORCiD redirects. If you want to get this working locally, you'll
need an SSL key and certificate file. For local testing, you can run the following to
generate them:

.. code-block:: console

    $ brew install mkcert
    $ brew install nss
    $ mkcert localhost 127.0.0.1 ::1
    $ mkcert -install

Then, these can be passed with the ``--ssl-keyfile`` and ``--ssl-certfile`` arguments.

*************************
 Putting it All Together
*************************

.. code-block:: console

    $ uv run main.py web --ssl-keyfile localhost+2-key.pem --ssl-certfile localhost+2.pem --live-login

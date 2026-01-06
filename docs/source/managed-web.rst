##################
 Login with ORCiD
##################

The SSSOM Curator web application can integrate ORCiD as an authentication system via
:mod:`flask_dance`.

First, register a public API client with ORCiD following the steps in the `first-party
guide
<https://info.orcid.org/documentation/integration-guide/registering-a-public-api-client/>`_
to fill out the form on https://orcid.org/developer-tools.

***********************
 Storing Configuration
***********************

This will give you two important strings: a client identifier and a client secret. If
you're testing locally, put these in a file `~/.config/sssom_curator.ini` with the
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
path `/login/orcid/authorized` in your app. For example, if you would like to test login
with ORCiD locally, then you can register a redirect in ORCiD's panel to
``https://127.0.0.1:8775/login/orcid/authorized``.

Note that ORCID doesn't allow using "localhost" as the host, so you have to use either
``127.0.0.1`` or ``0.0.0.0`` to make this work locally. In general, you can use any
resolvable host and port combination.

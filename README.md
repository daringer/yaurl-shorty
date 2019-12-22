# yaurl-shorty
Yet Another URL Shortener (REST API, yaml database, rate limited)

As plain as possible, still ready for the wild wild web. Obviously github 
has more than enough of these. Nevertheless, at least some distinctive features:

* REST API

	* get auto-created short-url: /gen/[long-url-starting-with-http]
	
	* choose any short-url: /[wish-short]/gen/[long-url-starting-with-http]
	
	* translate to long-url: /[short]

* backend database is a yaml-file

* rate of usage can be limited inside .yaml config

* yes, one can directly pass (append) the to-be-shortened-url into the address
  bar inside any browser to get a *shorty*-fied url (of your desire)


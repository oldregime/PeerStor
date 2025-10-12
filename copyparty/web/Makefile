# run me to zopfli all the static files
# which should help on really slow connections
# but then why are you using copyparty in the first place

pk: $(addsuffix .gz, $(wildcard tl/*.js *.js *.css))
un: $(addsuffix .un, $(wildcard tl/*.gz *.gz))

%.gz: %
	pigz -11 -J 34 -I 573 $<

%.un: %
	pigz -d $<

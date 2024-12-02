# libscrape
For scraping a site of English language PDF and EPUB files.

If there hypthetically were a site that hosted a huge number of PDF and EPUB files that were publically available but only indexed through a sketchy discord request bot function, and you noticed that the bot served the same domain with numbered subdirectories, and you tried going sequentially through the directories and found that it was all there, then this utility would go sequentially through and try to download everything English.

The tweaking I've got here is pretty good, it's not 100% but in general it skips the non-English files. 

It will track where it got to in COMPLETED.txt and try to pick back up from there. 

BASE_URL should be set to the domain that is hosting the link eg: "https://example.org/d/" 

PREFERRED_DOMAIN should be set to the domain that the PDFs are actually hosted on (what the BASE_URL points to)

I found I could run four separate terminal sessions with four separate directories with the script in it, one starting at 0-10000, one for 10000-20000, 20000-30000, 30000-40000. Then just leave it in a vm on a vpn and let it scrape away.  If you're too aggressive in the timing, you'll get throttled/blocked.

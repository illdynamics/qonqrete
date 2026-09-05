small tweak left to do please:
- lose that bar with the hazard stripes and the top to down text just right of the squid image on the bottom right of the web-interface. just remove that bar on the right of the image and make the image fill the space up until the corner.
- fix the config page, it is not loading the configuration at all now.
- lose the version string text on the bottom right at the squid image, we dont need it at all.
- fix the Act: status to be building instead of Ready for Review when partly waiting for review. we are always building until all tickets are ready to review and then we are reviewing so we dont need that ready to review status visually on the GUI.
- fix it so that the web-interface is not broken when it moves to the inspeQtor/reviewing.. I get a 502 now.

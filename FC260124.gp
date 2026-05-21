 #unset key;
 set term x11 1 persist;
 set multiplot; set origin 0.01,0.13; set size 0.99,0.82; set xtics format " ";
 set x2tics; set autoscale x2fix;set autoscale xfix;
 set key at screen 0.33,screen 0.7 font "0,9#for example;
 set title "2d / FE  / FC260124.ws5 \n\ 20240129 131556";
 set x2label "v (mm/s)";
 set ylabel "Relative Transmission";
 set label "Fit Param." at graph 0.70, graph 0.71 font "Arial,8";set label "Initial" at graph 0.81, graph 0.71 font "Arial,8";set label "Final" at graph 0.91, graph 0.71 font "Arial,8"; set label " 1" at graph 0.70, graph 0.6600 font "Arial,8"; set label " BKG(1)" at graph 0.72, graph 0.6600 font "Arial,8"; set label "********" at graph 0.81, graph 0.6600 font "Arial,8"; set label "********" at graph 0.91, graph 0.6600 font "Arial,8"; set label "14" at graph 0.70, graph 0.6250 font "Arial,8"; set label " WID" at graph 0.72, graph 0.6250 font "Arial,8"; set label " 0.11000" at graph 0.81, graph 0.6250 font "Arial,8"; set label " 0.34365" at graph 0.91, graph 0.6250 font "Arial,8"; set label "15" at graph 0.70, graph 0.5900 font "Arial,8"; set label " ARE" at graph 0.72, graph 0.5900 font "Arial,8"; set label " 0.05000" at graph 0.81, graph 0.5900 font "Arial,8"; set label " 0.19274" at graph 0.91, graph 0.5900 font "Arial,8"; set label "16" at graph 0.70, graph 0.5550 font "Arial,8"; set label " ISO" at graph 0.72, graph 0.5550 font "Arial,8"; set label "-0.10000" at graph 0.81, graph 0.5550 font "Arial,8"; set label "-0.10983" at graph 0.91, graph 0.5550 font "Arial,8"; set label "18" at graph 0.70, graph 0.5200 font "Arial,8"; set label " BHF" at graph 0.72, graph 0.5200 font "Arial,8"; set label "33.00000" at graph 0.81, graph 0.5200 font "Arial,8"; set label "33.00008" at graph 0.91, graph 0.5200 font "Arial,8"; set label "Area Percentajes" at graph 0.10, graph 0.51 font "Arial,8"; set label "1" at graph 0.10, graph 0.4600 font "Arial,8"; set label "       100.000000" at graph 0.12, graph 0.4600 font "Arial,8";
 plot "FC260124.dat" using 1:2 title "Experimental", "" using 1:3 with lines title "Total Fit" ;
 set origin 0.0,0.0; set size 1.0,0.2; unset label; unset title; unset x2tics; set xtics;
 set ylabel " ";
 unset x2label;
 unset key;
 plot "FC260124.dat" using 1: 4 title "REST"
 unset multiplot 

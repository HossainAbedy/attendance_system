<?php	
//if(!($mylink=mysql_connect("10.0.12.102","zkt","abc123X")))
if(!($mylink=mysql_connect("10.9.1.1","root","SbAc@123!")))
{
	print "<h3>couldnot connect database</h3>\n";
	exit;
	}	

	@mysql_select_db("hr_db", $mylink ) or die ("unable to locate database"); 
?>
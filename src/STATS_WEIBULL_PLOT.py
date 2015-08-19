#/***********************************************************************
# * Licensed Materials - Property of IBM 
# *
# * IBM SPSS Products: Statistics Common
# *
# * (C) Copyright IBM Corp. 2012, 2015
# *
# * US Government Users Restricted Rights - Use, duplication or disclosure
# * restricted by GSA ADP Schedule Contract with IBM Corp. 
# ************************************************************************/


__author__ = "SPSS, JKP"
__version__ = "1.1.6"

# history
# 21-feb-2012 original version
# 06-sep-2012 Add summary pivot table and allow saving of graph dataset
# 08-mar-2013 Ensure that the time variable is declared with scale measurement
# 11-apr-2013 Handle case where all records are failures
# 24-dec-2014 Keep work dataset variable names OLANG invariant
# 09-jan-2015 Add option for text file of chart points
# 27-mar-2015 Protect the copyTemplate function from permission problems

# function to create Weibull plot

helptext="""
Calculate and display three-parameter Weibull plot

STATS WEIBULL PLOT TIME=varname COUNT=varname
[TYPE=varname] [FAILURE="failure string"] [SUSPENSION="suspension string"]
[ITEMNAME=varname]
[/OPTIONS [TITLE="chart title"] [ANNOTATION="chart annotation"]]
[/SAVE GRAPHDS = dsname]
[/HELP]

Example:
STATS WEIBULL PLOT TIME=time TYPE=FailOrSusp COUNT=number.

TIME specifies the time of the observation from 0.  This is not an SPSS time
variable.  It could be measured in time units such as weeks, but it could also
be measured in terms of a measure such as number of usage cycles.  The
values must be positive.

COUNT specifies the count for each time period.  If no COUNT variable is
specified, each case counts as one.

TYPE is optional and specifies whether the case represents a failure or
a suspension, i.e. right-censored observation.  If it is omitted, all
cases are considered to be failures.

FAILURE and SUSPENSION specify the codes for the TYPE variable 
that define the type ofthe case.  They default to "F" and "S", respectively.  
Cases that do not match either of these codes are discarded for the analysis.

ITEMNAME can specifiy a variable containing the name of the item being
processed.  It will be used for labelling the output.

TITLE specifies a title for the chart.  If the text contains ")ID" and there
is an itemname, the itemname will replace that text.

ANNOTATION specifies an annotation that appears on the X axis.  The
date and time are automatically appended.

GRAPHDS specifies an optional dataset name.  If supplied, the dataset
containing the points plotted in the chart is retained under that name.

/HELP prints this information and does nothing else.
"""

suffix = ".viztemplate"

import spss, spssdata, spssaux
from extension import Template, Syntax, processcmd
import random, time
import os, sys
import shutil
import datetime

def weibull(timev, countv=None, etype=None, failcode="F", suspcode="S" , itemname=None, graphds = None, title="", annotation="", textfile=None, filemode="overwrite"):
    """Calculate and produce Weibull plot
    
    timev is the timestamp in whatever metric is desired.  It is not an SPSS time variable.
    countv is the total for that event.  Value is assumed to be 1 if not supplied
    etype indicates failure or suspension (right censoring).  If omitted, all events are assumed to be failures
    failcode and suspcode specify the strings defining failure and suspension
    title is the chart title
    annotation is text for annotation.  The current date/time will be appended
    
    Assumptions: 
    - there are enough failure datapoints to compute the regression
    
    Requires Statistics 19 hotfix for cLoglog scale or version 20 + fixpack1
    and weibull Graphboard template"""
    

    if title == "":
        title = _("""Weibull Plot""")
    activeds = spss.ActiveDataset()
    if  activeds == "*":    #unnamed
        activeds = "D." + str(random.uniform(0, 1))
        spss.Submit("DATASET NAME %s" % activeds)
    if graphds is None:
        workds = "D." + str(random.uniform(0,1))
    else:
        workds = graphds
    spss.Submit("""DATASET COPY %(workds)s WINDOW=HIDDEN.
DATASET ACTIVATE %(workds)s.""" % locals())
    descriptive = "D." + str(random.uniform(0,1))    # for OMS descriptives
    omstag = "D." + str(random.uniform(0,1))   # for OMS tag name
    omstag2 = "D." + str(random.uniform(0,1))   # for OMS tag name
    coefficients = "D." + str(random.uniform(0,1))   # for coeficients dataset
    modelsummary = "D." + str(random.uniform(0,1))   # for modelsummary dataset
    cumtotaln = "D." + str(random.uniform(0,1))   # for CumTotalN variable
    id = "D." + str(random.uniform(0,1))   # for id variable
    meanorder = "D." + str(random.uniform(0,1))   # for MeanOrder variable
    n = "D." + str(random.uniform(0,1))   # for N variable
    summaryds = "D." + str(random.uniform(0,1))  # for summary count dataset - 1 or 2 rows
    
    vardict = spssaux.VariableDict()
    execflag = False
    etype1 = etype
    if etype is None:
        execflag = True
        etype = "V." + str(random.uniform(0,1))
        spss.Submit("""STRING %(etype)s (A8).
COMPUTE %(etype)s = "%(failcode)s".""" % locals())
    if countv is None:
        execflag = True
        countv = "V." + str(random.uniform(0,1))
        spss.Submit("COMPUTE %(countv)s = 1." % locals())
    if execflag:      # EXECUTE is required so that DELETE VARIABLES can run
        spss.Submit("EXECUTE")
    keeplist = [timev, etype, countv]
    if itemname:
        keeplist.append(itemname)
        item = "/itemid=FIRST(%s)" % itemname
    else:
        item = ""
    trash = set([v.lower() for v in spssaux.VariableDict().variables]) - set([theitem.lower() for theitem in keeplist])
    if trash:
        spss.Submit("""DELETE VARIABLES %s.""" % " ".join(trash))
    
    if failcode < suspcode:
        sorder = "A"
    else:
        sorder = "D"
    try:
        # screen out any invalid values (watch out for that trailing decimal point)
        cmd=r"""SELECT IF (%(etype)s EQ "%(failcode)s" OR %(etype)s EQ "%(suspcode)s")
        AND %(timev)s GT 0 AND %(countv)s GE 0..
        * aggregate to collapse to unique cells.  We lose the hidden attribute here.
        AGGREGATE /OUTFILE=*
        /BREAK = %(timev)s %(etype)s
        /%(countv)s = SUM(%(countv)s) %(item)s.
        DATASET NAME %(workds)s.
        SORT CASES BY %(timev)s(A) %(etype)s(%(sorder)s).
    
    *** compute the cumulative number of cases.
    
    COMPUTE %(id)s=$CASENUM.
    Do if(%(id)s=1).
    compute %(cumtotaln)s=%(countv)s.
    ELSE. 
    compute %(cumtotaln)s=LAG(%(cumtotaln)s)+%(countv)s.
    END IF.
    
    *** compute the total number of cases in dataset incorporating frequency weight.
    
    DATASET DECLARE  %(descriptive)s. 
    OMS 
      /SELECT TABLES 
      /IF COMMANDS=['Descriptives'] SUBTYPES=['Descriptive Statistics'] 
      /DESTINATION FORMAT=SAV
       OUTFILE='%(descriptive)s' VIEWER=NO
      /TAG = "%(omstag)s".
     
    DESCRIPTIVES VARIABLES=%(cumtotaln)s 
      /STATISTICS= MAX.
    
    OMSEND TAG = "%(omstag)s".
    """
        try:
            spss.Submit(cmd % locals())
        except:
            raise ValueError(_("""All cases were filtered out by selection criteria or there was no data."""))
        
        # fix Maximum and N varnames from DESCRIPTIVES
        fixnames([4,5], ['N', 'Maximum'], descriptive)
        cmd = r"""DATASET ACTIVATE  %(workds)s.
MATCH FILES /FILE=*
      /FILE='%(descriptive)s'
      /RENAME (Maximum = %(n)s) 
      /DROP= Command_ Label_ N Subtype_  Var1.
      
    *  /RENAME (Command_ Label_ N Subtype_ TableNumber_ Var1 Maximum= d0 d1 d2 d3 d4 d5 N) 
    */DROP= d0 d1 d2 d3 d4 d5.
    
DATASET CLOSE %(descriptive)s.
DATASET ACTIVATE %(workds)s.
    
Do if(%(id)s>1).
    compute %(n)s=LAG(%(n)s).
END IF.
    
    *** compute the mean order number for each case.
    
    Do if(%(id)s=1 and %(etype)s='%(suspcode)s').
    compute %(meanorder)s=0.
    ELSE if(%(id)s=1 and %(etype)s='%(failcode)s'). 
    compute %(meanorder)s=%(cumtotaln)s.
    ELSE if(%(id)s>1 and %(etype)s='%(suspcode)s'). 
    compute %(meanorder)s=LAG(%(meanorder)s).
    ELSE if(%(id)s>1 and %(etype)s='%(failcode)s').
    compute %(meanorder)s=LAG(%(meanorder)s)+(%(n)s+1-LAG(%(meanorder)s))*%(countv)s/(1+%(n)s - LAG(%(cumtotaln)s)).
    END IF.
    
    *** compute the CDF, log(-log(1-F)) and log(time).
    
    compute #m=2*(%(n)s-%(meanorder)s + 1).
    compute #n=2*%(meanorder)s.
    if (#n > 0) F=1/(1+(%(n)s-%(meanorder)s+1)*IDF.F(0.5,#m,#n)/%(meanorder)s).
    compute cloglogF=LN(-Ln(1-F)).
    compute LnT=LN(%(timev)s).
    
    *** select the cases that are failure for regression model building.
    
    USE ALL.
    COMPUTE filter_$=(%(etype)s = '%(failcode)s').
    FILTER BY filter_$.""" % locals()
    
        spss.Submit(cmd)
        # fix Std.Error Beta t Sig AdjustedRSquare Std.ErroroftheEstimate B
		# In the code below, the regression output is checked specially
        # for the constant term.  This used to be done by looking for
        # a leading parenthesis in the variable name, but in some
        # output languages, the parenthesis character is not the
        # ascii (.  The code now expects the constant term to be
        # the first variable.

        cmd=r"""
    ***compute x = %(timev)s.
    compute y = F.
    ***variable level x (scale).
    
    *** build regression model. Here the dependent is LnT and predictor is LnLnInvOneminusF, RRX.
    
    DATASET DECLARE  %(modelsummary)s.
    OMS
      /SELECT TABLES
      /IF COMMANDS=['Regression'] SUBTYPES=['Model Summary']
      /DESTINATION FORMAT=SAV
       OUTFILE='%(modelsummary)s'
      /TAG = "%(omstag)s".
    
    DATASET DECLARE  %(coefficients)s.
    OMS
      /SELECT TABLES
      /IF COMMANDS=['Regression'] SUBTYPES=['Coefficients']
      /DESTINATION FORMAT=SAV
       OUTFILE='%(coefficients)s'
       /TAG = "%(omstag2)s".
    
    REGRESSION
      /MISSING LISTWISE
      /STATISTICS COEFF R 
      /CRITERIA=PIN(.05) POUT(.10)
      /NOORIGIN 
      /DEPENDENT LnT
      /METHOD=ENTER cloglogF.
    
    omsend tag=["%(omstag)s" "%(omstag2)s"].
    
    DATASET ACTIVATE  %(workds)s.""" % locals()
        spss.Submit(cmd)
        fixnames([5,6,7,8,9], ['B','Std.Error','Beta','t','Sig'],
            coefficients)
        fixnames([4,5,6,7], ['R', 'RSquare','AdjustedRSquare',
            'Std.ErroroftheEstimate'], modelsummary)
        spss.Submit("""DATASET ACTIVATE %s.""" % workds)
        cmd=r"""
    MATCH FILES /FILE=*
      /FILE='%(coefficients)s'
     /RENAME (Var2=ParaName)
      /DROP=  Command_ Subtype_ Label_ Var1 Std.Error Beta t Sig.
    DATASET CLOSE %(coefficients)s.""" % locals()
        spss.Submit(cmd)
        cmd = r"""
    MATCH FILES /FILE=*
      /FILE='%(modelsummary)s'
    /DROP=  Command_ Subtype_ Label_ Var1 AdjustedRSquare Std.ErroroftheEstimate.
    DATASET CLOSE %(modelsummary)s.""" % locals()
        spss.Submit(cmd)
        cmd = r"""
    *** compute the parameters Beta and Eta.
    
    Do if(ParaName='cloglogF').
    compute  Beta=1/B.
    ELSE.
    compute Beta=$SYSMIS.
    END IF.
    FORMATS Beta (f16.8).
    * Paren check for (constant).
    do if ($casenum = 1).
    compute  Eta=exp(B).
    ELSE.
    compute Eta=$SYSMIS.
    FORMATS Eta (f16.8).
    END IF.
    EXECUTE.""" % locals()
    
        spss.Submit(cmd)
        # get parameters for insertion into chart footnote
        
        spss.Submit("FILTER OFF")   # ensure that first two absolute cases can be read
        
        curs = spssdata.Spssdata(indexes=["R", "Beta", "Eta"])
        r, ignore, eta = curs.fetchone()
        ignore, beta, ignore = curs.fetchone()
        curs.CClose()
        # get failure and suspension totals
        if etype1:
            breakspec = "/BREAK=%(etype)s" % locals()
        else:
            breakspec = ""
        if countv:
            totals = "sum(%(countv)s)" % locals()
        else:
            totals = "N"
    
        # calcuate summary statistics
	if item:
	    item = "/itemid=FIRST(itemid)"
        spss.Submit(r"""DATASET DECLARE %(summaryds)s.
        AGGREGATE OUTFILE= "%(summaryds)s" %(breakspec)s /total=%(totals)s %(item)s.
        DATASET ACTIVATE %(summaryds)s.""" % locals())
        
	curs = spssdata.Spssdata()
        summaries = curs.fetchall()
	curs.CClose()
        if itemname:
            itemid = summaries[0][-1]
        else:
            itemid = ""
        spss.StartProcedure(_("Weibull Plot"), "Weibull Plot")
        if itemname:
            tbltitle = _("Summary Failure Statistics: %s") % itemid
            rowlabel = [itemid]
        else:
            tbltitle = _("Summary Failure Statistics")
            rowlabel = [""]
        tbl = spss.BasePivotTable(tbltitle, "WEIBULLSUMMARY")
        # one row
        # columns: failure kt, suspension kt, total kt, beta, eta, R

        collabels = [_("Failures"), _("Suspensions"), _("Total"), _("Beta"), _("Eta"), _("R")]
        if failcode:
            collabels[0] = collabels[0] + _(" (%s)") % failcode
        if suspcode:
            collabels[1] = collabels[1] + _(" (%s)") % suspcode
        if len(summaries) == 1:   # everything is a failure
            failcount = summaries[0][1]
            suspcount = 0
        else:
            if summaries[0][0] == failcode:
                failcount = summaries[0][1]
                suspcount = summaries[1][1]
            else:
                failcount = summaries[1][1]
                suspcount = summaries[0][1]
        totalcount = failcount + suspcount
        tbl.SimplePivotTable(rowdim = "", rowlabels = rowlabel, coldim=_("Statistics"),
            collabels=collabels, cells = [failcount, suspcount, totalcount, beta, eta, r])
        spss.EndProcedure()
        
        spss.Submit("""DATASET CLOSE %(summaryds)s.
        DATASET ACTIVATE %(workds)s.
        FILTER BY filter_$""" % locals())
        
        
        
        curdate = time.asctime()
        if title and itemid:
            title = title.replace(")ID", itemid)

        footnote = r"""beta = %(beta).4f, eta = %(eta).4f, R = %(r).4f\n%(annotation)s %(curdate)s""" % locals()
        # updated for template supporting major/minor grid line styles to 4b from 4
        cmd2 = r"""VARIABLE LEVEL %(timev)s (SCALE).
        GGRAPH
    /GRAPHDATASET NAME="graphdataset"
      VARIABLES=y[LEVEL=ratio] %(timev)s [LEVEL=ratio] 
      MISSING=LISTWISE REPORTMISSING=NO
    /GRAPHSPEC SOURCE=VIZTEMPLATE(NAME="Weibull"[LOCATION=LOCAL]
      MAPPING( "X"="%(timev)s"[DATASET="graphdataset"] "Y"="y"[DATASET="graphdataset"] 
      "Footnote"="%(footnote)s" 
      "Title"="%(title)s"))
      VIZSTYLESHEET="Traditional"[LOCATION=LOCAL]
      LABEL='Weibull'
      DEFAULTTEMPLATE=NO.""" % locals()

	spss.Submit("""DELETE VARIABLES %(id)s TO cloglogF ParaName""" % locals())
	savetext(textfile, filemode)  # noop if no file specified
	if graphds is None:
	    spss.Submit("""DATASET CLOSE %(workds)s.""" % locals())	
        try:
            spss.Submit(cmd2)
        except:
            raise SystemError(_("""The required template was not found or the required Statistics update is not installed.
            This procedure requires the Graphboard template Weibull.viztemplate.  It also requires at least Statistics version 20 
            with fixpack1 or a later version.  For Statistics 19, it needs the hotfix for the cloglog scale."""))
    finally:
        spss.EndProcedure()   # just in case
        spss.Submit("DATASET ACTIVATE %(activeds)s." % locals())

# language invariant cleanup
# used to ensure English variable names in OMS datasets
# regardless of OLANG setting
def fixnames(indexes, newnames, dsname=None):
    """Rename the variables at position
    
    indexes is a sequence of the variable dictionary locations
    newnames is a sequence of the names to assign
    dsname optionally specifies a dataset to activate first"""

    if not dsname is None:
        spss.Submit("""DATASET ACTIVATE %s.""" % dsname)
    oldnames = [spss.GetVariableName(loc) for loc in indexes]
    spss.Submit("""RENAME VARIABLES (%s = %s)""" % \
        (" ".join(oldnames), " ".join(newnames)))

def savetext(filename, filemode):
    """Save the current dataset as a text file
    
    filename is the path for the file
    filemode is overwrite or append
    
    If filename is None, this is a no-op"""
    
    if filename is None:
	return
    fm = filemode == "overwrite" and "wb" or "ab"

    opened = False
    with spssdata.Spssdata(names=False) as curs:
	for case in curs:
	    if not opened:
		opened = True
		f = open(filename, fm)
		nvar = len(case)
	    lcase = []
	    for item in case:
		if item is None:
		    lcase.append("")
		elif isinstance(item, basestring):
		    lcase.append(spssaux._smartquote(item.rstrip()))
		else:
		    lcase.append(str(item))
	    lcase.append("\n")
	    case = ",".join(lcase)
	    f.write(case)
	f.close()
	
def Run(args):
    """Execute the STATS WEIBULL PLOT command"""

    args = args[args.keys()[0]]
    ###print args   #debug
    
    ###debugging
    #try:
        #import wingdbstub
        #if wingdbstub.debugger != None:
            #import time
            #wingdbstub.debugger.StopDebug()
            #time.sleep(2)
            #wingdbstub.debugger.StartDebug()
    #except:
        #pass

    oobj = Syntax([
        Template("TIME", subc="",  ktype="existingvarlist", var="timev", islist=False),
        Template("TYPE", subc="",  ktype="literal", var="etype"),
        Template("COUNT", subc="",  ktype="existingvarlist", var="countv"),
        Template("FAILURE", subc="", ktype="literal", var="failcode"),
        Template("SUSPENSION", subc="", ktype="literal", var="suspcode"),
        Template("ITEMNAME", subc="", ktype="existingvarlist", var="itemname"),
        
        Template("ANNOTATION", subc="OPTIONS", ktype="literal", var="annotation"),
        Template("TITLE", subc="OPTIONS", ktype="literal", var="title"),
        
        Template("GRAPHDS", subc="SAVE", ktype="varname", var="graphds"),
        Template("TEXTFILE", subc="SAVE", ktype="literal", var="textfile"),
        Template("FILEMODE", subc="SAVE", ktype="str", var="filemode",
            vallist=["overwrite", "append"]),
        Template("HELP", subc="", ktype="bool")])
    
        # ensure localization function is defined
    global _
    try:
        _("---")
    except:
        def _(msg):
            return msg

    copyTemplate("Weibull")
        # A HELP subcommand overrides all else
    if args.has_key("HELP"):
        #print helptext
        helper()
    else:
        processcmd(oobj, args, weibull, vardict=spssaux.VariableDict())

def getVizTemplatePath(templateName):
    vizPath = os.path.expanduser("~")
    if sys.platform == 'win32':
        vizPath = vizPath + "\\Application Data\\SPSSInc\\Graphboard\\templates\\"
    elif sys.platform.lower().find('darwin') > -1:
        vizPath = vizPath + "/Library/Application Support/SPSSInc/Graphboard/templates/"
    else:
        vizPath = vizPath + "/.Graphboard/templates/"

    vizPath = vizPath + templateName + suffix
    return vizPath

def copyTemplate(templateName):
	dst = getVizTemplatePath(templateName)
	path = os.path.splitext(__file__)[0]
	templateFile = path + os.path.sep + templateName + suffix
	# If the file exists and is read only or the target location is
	# not writeable, the code below will fail.  We simply ignore
	# that here.  The user will have to install the template manually
	try:
		if os.path.isfile(dst):
			time1 = os.path.getmtime(dst)
			time2 = os.path.getmtime(templateFile)
			if time1 == time2:
				pass
			else:
				shutil.copy2(templateFile, dst)
		else:
			shutil.copy2(templateFile, dst)
	except:
		pass


def helper():
    """open html help in default browser window
    
    The location is computed from the current module name"""
    
    import webbrowser, os.path
    
    path = os.path.splitext(__file__)[0]
    helpspec = "file://" + path + os.path.sep + \
         "markdown.html"
    
    # webbrowser.open seems not to work well
    browser = webbrowser.get()
    if not browser.open_new(helpspec):
        print("Help file not found:" + helpspec)
try:    #override
    from extension import helper
except:
    pass

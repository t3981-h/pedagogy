from flask import g
from flask_login import current_user
from app import app
from app.models import Employee, Workshop, Response
import altair as alt
from altair import expr, datum
import pandas as pd
from config import conn

df = pd.read_sql_query(
    "SELECT workshop.id, workshop_name, workshop_category, workshop_instructor, workshop_start, workshop_hours, class_size, e.name FROM workshop LEFT JOIN employee as e ON e.id = workshop.workshop_instructor", conn, index_col='id')
# convert datetime to '2018-09' month and year format
df['mnth_yr'] = df['workshop_start'].dt.to_period('M').astype(str)
df['workshop_category'] = df['workshop_category'].astype('category')

@app.before_request
def before_request():
    if current_user.is_authenticated:
        employee = Employee.query.filter_by(email=current_user.email).first()
        if employee is not None:
            df['this_user'] = df['workshop_instructor'] == employee.id
            g.user_melted = pd.melt(
                df[df['this_user'] == True],
                id_vars=['mnth_yr', 'workshop_category'], 
                value_vars=['workshop_hours', 'class_size'])       
    
            g.df3 = df[df['this_user'] == True].copy()
            g.df3['workshop_category'] = pd.Categorical(g.df3['workshop_category']).codes
            g.dat2 = g.df3.set_index('workshop_start').resample('W').sum()
            g.accum_personal = pd.melt(g.dat2.reset_index(), 
                id_vars=['workshop_start','workshop_category'], 
                value_vars=['workshop_hours', 'class_size'])
            g.accum_personal['workshop_category'] = g.accum_personal['workshop_category'].apply(lambda x: 'Corporate' if (x == 1) else 'Public')
            g.accum_personal['cumsum'] = g.accum_personal.groupby(['variable','workshop_category']).cumsum().fillna(0)
        
    g.df2 = df.copy()
    g.df2['workshop_category'] = pd.Categorical(g.df2['workshop_category']).codes
    g.df2['workshop_category'] = g.df2['workshop_category'].astype('category')
    
    g.dat = df[['workshop_start','workshop_category', 'workshop_hours', 'class_size']].copy()
    g.dat['workshop_category'] = pd.Categorical(g.dat['workshop_category']).codes
    g.dat['workshop_category'] = g.dat['workshop_category'].astype('category')

    g.dat['workshop_category'] = g.dat['workshop_category'].apply(lambda x: 'Corporate' if (x == 1) else 'Public')
    g.dat = g.dat.set_index(
        'workshop_start').groupby(
            'workshop_category').resample('W').sum()
    g.dat.sort_index(inplace=True)

    g.accum = pd.melt(g.dat.reset_index(), 
            id_vars=['workshop_start','workshop_category'], 
            value_vars=['workshop_hours', 'class_size'])
    g.accum['cumsum'] = g.accum.groupby(['variable','workshop_category']).cumsum()
    g.accum = g.accum.sort_values(['workshop_category', 'workshop_start'])

    g.accumtotal = df[['workshop_start', 'class_size']].copy().set_index('workshop_start').sort_index().reset_index()
    g.accumtotal['cumsum'] = g.accumtotal['class_size'].cumsum()

@app.route('/data/class_size_vs')
def class_size_vs():
    brush = alt.selection(type='interval', encodings=['x'])
    upper = alt.Chart(df[df['this_user'] == True]).mark_area(
    clip=True,
    opacity=0.75,
    interpolate='monotone'
    ).encode(
        x=alt.X("mnth_yr:T", axis=alt.Axis(title=''), scale={'domain':brush.ref()}),
        y=alt.Y('sum(workshop_hours)', axis=alt.Axis(title='Workshop Hours')),
        color=alt.Color(
            'workshop_category',
            scale=alt.Scale(range=['#1a1d21', '#7dbbd2cc', '#153f5a', '#bbc6cbe6']),
            #'#7dbbd2cc', '#bbc6cbe6'
            legend=None
        ),
        tooltip=['workshop_category']
    ).properties(width=450)
    lower = alt.Chart(df[df['this_user'] == True]).mark_rect(color='#75b3cacc').encode(
        x=alt.X("mnth_yr:T", axis=alt.Axis(title='Interval Selector'), scale={'domain':brush.ref()})
    ).add_selection(
        brush
    ).properties(width=450)
    chart = alt.vconcat(upper, lower, data=df[df['this_user'] == True])
    return chart.to_json()

@app.route('/data/class_size_hours')
def class_size_hours():
    chart = alt.Chart(g.user_melted).mark_bar().encode(
        column='variable',
        x=alt.X("sum(value)"),
        y=alt.Y('mnth_yr'),
        color=alt.Color(
            'workshop_category',
            scale=alt.Scale(range=['#7dbbd2cc', '#bbc6cbe6', '#6eb0ea', '#d1d8e2', '#1a1d21', '#8f9fb3' ]),legend=None),
            tooltip=['workshop_category', 'sum(value)']
        ).properties(
            width=250
        )
        
    return chart.to_json()

@app.route('/data/accum_global')
def accum_global():
    chart = alt.Chart(g.accum).mark_area().encode(
        column=alt.Column('workshop_category', title=None, sort="descending", 
                          header=alt.Header(titleColor='red', labelColor='red', titleAnchor="end")),
        x=alt.X("workshop_start", title="Date"),
        y=alt.Y("cumsum:Q", title="Cumulative"),
        color=alt.Color("variable", 
            scale=alt.Scale(
                range=['#7dbbd2cc', '#bbc6cbe6']),
            legend=None
        ),
        tooltip=['variable', 'cumsum:Q']
    ).properties(width=350).configure_axis( 
        labelColor='#bbc6cbe6',titleColor='#bbc6cbe6'
    )
    return chart.to_json()

@app.route('/data/accum_global_line')
def accum_global_line():
    brush = alt.selection(type='interval', encodings=['x'])
    # Create a selection that chooses the nearest point & selects based on x-value
    nearest = alt.selection(type='single', nearest=True, on='mouseover',
                            fields=['workshop_start'], empty='none')
    line = alt.Chart().mark_line(color='#cccccc', interpolate='basis').encode(
            x=alt.X("workshop_start:T", axis=alt.Axis(title='', grid=False),scale={'domain': brush.ref()}),
            y=alt.Y("cumsum", axis=alt.Axis(title='Total Students', grid=False))
    )
    selectors = alt.Chart(g.accumtotal).mark_point().encode(
        x=alt.X("workshop_start:T"),
        opacity=alt.value(0)
    ).add_selection(
        nearest
    )
    points = line.mark_point().encode(
        opacity=alt.condition(nearest, alt.value(1), alt.value(0))
    )
    text = line.mark_text(align='left', dx=-20, dy=-5).encode(
        text=alt.condition(nearest, 'cumsum:Q', alt.value(' '))
    )
    rules = alt.Chart().mark_rule(color='gray').encode(
        x=alt.X("workshop_start:T"),
    ).transform_filter(
        nearest
    )

    upper = alt.layer(line, selectors, points, rules, text, data=g.accumtotal, width=350)
    lower = alt.Chart().mark_area(color='#75b3cacc').encode(
            x=alt.X("workshop_start:T", axis=alt.Axis(title=''), scale={
                'domain':brush.ref()
            }),
            y=alt.Y("cumsum", axis=alt.Axis(title=''))
        ).properties(
        height=30,
        width=350
    ).add_selection(
        brush
    )

    chart = alt.vconcat(upper,lower, data=g.accumtotal).configure_view(
        strokeWidth=0
    )
    return chart.to_json()

@app.route('/data/accum_personal')
def accum_personal():
    chart = alt.Chart(g.accum_personal).mark_area().encode(
        column='workshop_category',
        x=alt.X("workshop_start"),
        y=alt.Y("cumsum:Q"),
        color=alt.Color("variable", 
            scale=alt.Scale(
                range=['#7dbbd2cc', '#bbc6cbe6']),
            legend=None
        ),
        tooltip=['variable', 'cumsum:Q']
    ).properties(
        width=250
    )
    return chart.to_json()

@app.route('/data/punchcode')
def punchcode():
    g.df2['workshop_category'] = g.df2['workshop_category'].apply(lambda x:'Corporate' if x == 1 else 'Public' )
    g.df2['contrib'] = g.df2['workshop_hours'] * g.df2['class_size']

    chart = alt.Chart(g.df2[g.df2.name != 'Capstone']).mark_circle(color='#bbc6cbe6').encode(
        x=alt.X('mnth_yr:T', axis=alt.Axis(title='')),
        y='name:O',
        size=alt.Size('sum(contrib):Q', legend=None),
        column=alt.Column('workshop_category:O', title=None, sort="descending", 
            header=alt.Header(titleColor='#bbc6cbe6', labelColor='#bbc6cbe6', labelAngle=30, titleFontSize=40, titleAngle=30))
    ).properties(
        width=300, height=320
    ).configure_axis( 
        labelColor='#bbc6cbe6', titleColor='#bbc6cbe6'
    )
    return chart.to_json()

@app.route('/data/category_bars')
def category_bars():
    chart = alt.Chart(df).mark_bar(color='#bbc6cbe6').encode(
        x=alt.X('sum(workshop_hours):Q', title='Accumulated Hours'),
        y=alt.Y('workshop_category:O', title=''),
        tooltip=['sum(workshop_hours):Q', 'workshop_category:O']
    )
    return chart.to_json()

@app.route('/data/instructor_breakdown')
def instructor_breakdown():
    # Getting Responses Data
    q = """ SELECT response.*, workshop_category, name
            FROM response
            INNER JOIN workshop as w 
                ON w.id = response.workshop_id
            INNER JOIN employee as e
                ON w.workshop_instructor = e.id
        """
    responses = pd.read_sql_query(
        q,
        conn,
        index_col='id'
    )
    resp_nw = responses[responses['workshop_category'] != 'Weekend'].groupby('name').agg('mean').round(2).sort_values('knowledge', ascending=False)
    resp_nw['total'] = resp_nw.iloc[:,1:].mean(axis=1).round(2)
    resp_nwm = pd.melt(resp_nw.iloc[:,1:].reset_index(), id_vars='name')

    multi = alt.selection_multi(fields=['name'], on='click')
    brush = alt.selection(type='interval')
    color = alt.condition(multi, alt.Color('name:N',  legend=None), alt.value('lightgray'))
    color2 = alt.condition(brush, alt.Color('name:N',  legend=None), alt.value('lightgray'))
    point = alt.Chart(df).mark_circle(size=60).encode(
        x=alt.X('workshop_start:T', axis=alt.Axis(title='')),
        y=alt.Y('sum(class_size)', axis=alt.Axis(title='Class Size', grid=False)),
        color=alt.Color('name:N', legend=None),
        tooltip=['workshop_name','monthdate(workshop_start)', 'name','class_size']
    ).transform_filter(
        multi
    ).transform_filter(
        brush
    ).properties(
        width=600
    ).interactive()
    bar = alt.Chart(df).mark_bar().encode(
        x=alt.X('sum(workshop_hours):Q', title='Accumulated Hours'),
        y=alt.Y('workshop_category:O', title=''),
        color=alt.Color('name:N', legend=None),
        tooltip=['sum(workshop_hours):Q', 'workshop_category:O']
    ).transform_filter(
        brush
    ).transform_filter(
        multi
    )
    box = alt.Chart(df).mark_rect().encode(
        x=alt.X('class_size:Q', bin=alt.Bin(maxbins=15)),
        y=alt.Y('workshop_hours:Q', bin=alt.Bin(maxbins=15)),
        color=color2,
        size=alt.Size('sum(workshop_hours):Q', legend=None),
        tooltip=['workshop_name:O', 'class_size:Q']
    ).transform_filter(
        multi
    ).add_selection(
        brush
    )
    picker = alt.Chart(df).mark_rect().encode(
        y=alt.Y('name:N'),
        color=color, 
    ).add_selection(
        multi
    )

    a = alt.Chart(resp_nwm).mark_square(size=40).encode(
        x=alt.X('variable:N', scale=alt.Scale(rangeStep=80), axis=alt.Axis(labelAngle=0)),
        y=alt.Y('value'),
        color=alt.Color('name', legend=None),
        tooltip=['name','value']
    ).transform_calculate(
        value=expr.round(expr.exp(datum.value))
    ).transform_filter(
        multi
    )

    b = a.mark_line(opacity=0.8, interpolate='monotone').encode(
        x=alt.X('variable')
    )
    chart = picker | (point & a+b) | (box & bar)
    #chart = alt.hconcat(picker, alt.vconcat(point, a+b) , alt.vconcat(box, bar))
    return chart.to_json()


@app.route('/data/mediumos')
def mediumos():
    home = pd.read_csv('data/home.csv')
    chart = alt.Chart(home).mark_bar().encode(
        x='Medium',
        y='count()',
        column='OSGroup',
        color='Medium'
    )
    return chart.to_json()

@app.route('/data/studentprof')
def studentprof():
    academy = pd.read_csv('data/academy.csv')
    chart = alt.Chart(academy).mark_bar().encode(
        # rangeStep allocates 20px for each bar
        alt.X('Medium:N', scale=alt.Scale(rangeStep=20), axis=alt.Axis(title='')),
        alt.Y('count():Q', axis=alt.Axis(title='Observations', grid=False)),
        column='OSGroup:N',
        color=alt.Color(
            'Are you a student or a professional?:N',
            scale=alt.Scale(range=["#EA98D2", "#659CCA"]))
    ).configure_axis(
        domainWidth=0.8
    )
    return chart.to_json()

# ================ Non-Chart Section ================
# Return Stats, usually in the form of Dictionary
# ===================================================

def global_total_stats():
    stats = {
        'students': df['class_size'].sum(),
        'workshops': df.shape[0],
        'studenthours': sum(df['workshop_hours']),
        # 'studenthours': sum(df['workshop_hours'] * df['class_size']),
        'companies': sum(df['workshop_category'] == 'Corporate'),
        'instructors': len(df['workshop_instructor'].unique()),
        'topten': g.df2[g.df2.name != 'Capstone'].loc[:,['name','workshop_hours', 'class_size']].groupby(
            'name').sum().sort_values(
                by='workshop_hours', 
                ascending=False).head(10).rename_axis(None).to_html(classes=['table thead-light table-striped table-bordered table-hover table-sm'])
    }
    return stats

def person_total_stats():
    workshops = Workshop.query.filter_by(
        workshop_instructor=g.employee.id).order_by(Workshop.workshop_start.desc())
    grped = dict()
    totalstud = 0
    totalhours = 0
    for gr in workshops:
        category = gr.workshop_category
        if category not in grped:
            grped[category] = {'count': 0, 'students': 0, 'hours': 0}
        grped[category]['count'] += 1
        grped[category]['students'] += gr.class_size
        grped[category]['hours'] += gr.workshop_hours
        totalhours += gr.workshop_hours
        totalstud += gr.class_size

    responses = Response.query.filter(Response.workshop_id.in_(w.id for w in workshops)).all()
    fullstar = Response.query.filter(Response.workshop_id.in_(w.id for w in workshops), Response.satisfaction_score + Response.knowledge >= 9).count()

    # for qualitative reviews
    qualitative = Response.query.filter(
        Response.workshop_id.in_(w.id for w in workshops), Response.comments != '').join(
            Workshop, isouter=True).order_by(
                Workshop.workshop_start.desc()).paginate(
                    per_page=20, page=1, error_out=True)

    stats = {
        'employee': g.employee,
        'workshops': workshops.limit(5),
        'responses': responses,
        'grped': grped,
        'totalstud': totalstud,
        'totalhours': totalhours,
        'totalws': workshops.count(),
        'fullstar': fullstar,
        'responsecount': len(responses),
        'qualitative': qualitative,
        'topten': g.df2[g.df2.name != 'Capstone'].loc[:,['name','workshop_hours', 'class_size']].groupby(
            'name').sum().sort_values(
                by='workshop_hours', 
                ascending=False).head(10).rename_axis(None).to_html(classes=['table thead-light table-striped table-bordered table-hover table-sm'])

    }
    return stats
import re
import hmac
import webapp2
from google.appengine.ext import db
from user import User
from post import Post
from comment import Comment
from like import Like
import helper

secret = 'blablablatraah45'


def make_secure_val(val):
    """
    this method expects a string as input,
    the function return the initial srting 
    and a hmac hashing (with a secret) in a hexdecimal format
    """
    return '%s|%s' % (val, hmac.new(secret, val).hexdigest())


def check_secure_val(secure_val):
    """
    verify if hash saved in cookie is correct:
    expects in input a string (from cookie)
    returns the undecoded val if the hashing is correct
    """
    val = secure_val.split('|')[0]
    if secure_val == make_secure_val(val):
        return val

def login_required(func):
    ''' 
    wrapper decorator to verify if user is logged in, if not redirect
    '''
    def login(self, *args, **kwargs):
        if not self.user:
            self.redirect("/login?error=you are not logged in!")
        else:
            func(self, *args, **kwargs)
    return login

class BlogHandler(webapp2.RequestHandler):
    def write(self, *a, **kw):
        self.response.out.write(*a, **kw)

    def render_str(self, template, **params):
        params['user'] = self.user
        return helper.jinja_render_str(template, **params)

    def render(self, template, **kw):
        self.write(self.render_str(template, **kw))

    def set_secure_cookie(self, name, val):
        """
        set cookies in the header
        input 2 strings: 
        name of the cookie and value of the cookie
        """
        cookie_val = make_secure_val(val)
        self.response.headers.add_header(
            'Set-Cookie',
            '%s=%s; Path=/' % (name, cookie_val))

    def read_secure_cookie(self, name):
        cookie_val = self.request.cookies.get(name)
        return cookie_val and check_secure_val(cookie_val)

    def login(self, user):
        self.set_secure_cookie('user_id', str(user.key().id()))

    def logout(self):
        self.response.headers.add_header('Set-Cookie', 'user_id=; Path=/')

    def initialize(self, *a, **kw):
        webapp2.RequestHandler.initialize(self, *a, **kw)
        uid = self.read_secure_cookie('user_id')
        self.user = uid and User.by_id(int(uid))


def blog_key(name='default'):
    return db.Key.from_path('blogs', name)

class NotFound(BlogHandler):
    def get(self):
        error = self.request.get('error')
        self.render("404.html", error=error)

class BlogFront(BlogHandler):
    """
    class BlogFront 
    homepage handler 
    shows all posts from most recent 
    """
    def get(self):
        deleted_post_id = self.request.get('deleted_post_id')
        posts = greetings = Post.all().order('-created')
        self.render('front.html', posts=posts, deleted_post_id=deleted_post_id)


class PostPage(BlogHandler):
    def get(self, post_id):
        """
        render a specific post with all comments and likes
        """
        if post_id:
            key = db.Key.from_path('Post', int(post_id), parent=blog_key())
            post = db.get(key)

            if not post:
                self.error(404)
                return self.redirect('not_found' + "?error= the post was not found")
            else:
                # comments = db.Query(Comment).filter('post_id =', post.key().id()).order('-created')
                comments = db.GqlQuery("select * from Comment where post_id =" +
                                        post_id + " order by created desc")
                likes = db.GqlQuery("select * from Like where post_id="+post_id)
                error = self.request.get('error')
                return self.render("permalink.html", post=post, numLikes=likes.count(), error=error, comments=comments)
        else:
            self.error(404)
            return self.redirect('not_found' + "?error= the post was not found")

    @login_required
    def post(self, post_id):

        if post_id:
            key = db.Key.from_path('Post', int(post_id), parent=blog_key())
            post = db.get(key)

            if not post:
                self.error(404)
                return self.redirect('not_found' + "?error= something went wrong")
            c = ""

            # update likes on lick-click
            if(self.request.get('like') and
             self.request.get('like') == "update"):
                likes = db.GqlQuery("select * from Like where post_id = " +
                                post_id + " and user_id = " +str(self.user.key().id()))

                if self.user.key().id() == post.user_id:
                    return self.redirect("/blog/" + post_id +
                                        "?error=You cannot like your post!")
                #one can only like a post once
                elif likes.count() == 0:
                    l = Like(parent=blog_key(), user_id=self.user.key().id(),
                       post_id=int(post_id))
                    l.put()

            if(self.request.get('comment')):
                c = Comment(parent=blog_key(), user_id=self.user.key().id(),
                            post_id=int(post_id),
                            comment=self.request.get('comment'))
                c.put()

            comments = db.GqlQuery("select * from Comment where post_id = " +
                                   post_id + "order by created desc")

            likes = db.GqlQuery("select * from Like where post_id="+post_id)

            self.render("permalink.html", post=post,
                        comments=comments, numLikes=likes.count(),
                        new=c)
        else: 
            self.error(404)
            return self.redirect('not_found' + "?error= the post was not found")


class NewPost(BlogHandler):
    @login_required
    def get(self):
        self.render("newpost.html")
        
    @login_required
    def post(self):
        """
        create new post and redirect to this page
        after successful creation
        """
        subject = self.request.get('subject')
        content = self.request.get('content')

        if subject and content:
            p = Post(parent=blog_key(), user_id=self.user.key().id(),
                     subject=subject, content=content)
            p.put()
            self.redirect('/blog/%s' % str(p.key().id()))
        else:
            error = "subject and content, please!"
            self.render("newpost.html", subject=subject,
                        content=content, error=error)


class DeletePost(BlogHandler):
    @login_required
    def get(self, post_id):
        if post_id:
            key = db.Key.from_path('Post', int(post_id), parent=blog_key())
            post = db.get(key)
            if not post:
                return self.redirect("/login")
            else:
                if post.user_id == self.user.key().id():
                    post.delete()
                    self.redirect("/?deleted_post_id="+post_id)
                else:
                    self.redirect("/blog/" + post_id + "?error=You don't have " +
                                  "access to delete this record.")


class EditPost(BlogHandler):
    
    @login_required
    def get(self, post_id):
        """
        update post content
        """
        if post_id:
            key = db.Key.from_path('Post', int(post_id), parent=blog_key())
            post = db.get(key)
            if post:
                if post.user_id == self.user.key().id():
                    self.render("editpost.html", subject=post.subject,
                                content=post.content)
                else:
                    self.redirect("/blog/" + post_id + "?error=You don't have " +
                                  "access to edit this record.")
            else:
                self.redirect("/login?error=post does not exists")
        else:
            self.redirect("/login?error=post does not exists")

    @login_required
    def post(self, post_id):        
        if post_id:
            key = db.Key.from_path('Post', int(post_id), parent=blog_key())
            post = db.get(key)
            if post:                
                if post.user_id == self.user.key().id():

                    subject = self.request.get('subject')
                    content = self.request.get('content')

                    if subject and content:
                        post.subject = subject
                        post.content = content
                        post.put()
                        self.redirect('/blog/%s' % post_id)
                    else:
                        error = "subject and content, please!"
                        self.render("editpost.html", subject=subject,
                                    content=content, error=error)
                else:
                    self.redirect("/login?error=the post does not exists")
            else: 
                self.redirect("/login?error=the post does not exists")
        else:
            self.redirect("/blog/" + post_id + "?error=You don't have " +
                            "access to edit this record.")



class DeleteComment(BlogHandler):

    @login_required
    def get(self, post_id, comment_id):
        """
        delete comment based on id of a post (post_id)
        """
        if post_id and comment_id:
            key = db.Key.from_path('Comment', int(comment_id),
                                   parent=blog_key())
            c = db.get(key)
            if c:
                if c.user_id == self.user.key().id():
                    c.delete()
                    self.redirect("/blog/"+post_id+"?deleted_comment_id=" +
                                  comment_id)
                else:
                    self.redirect("/blog/" + post_id + "?error=You don't have " +
                                  "access to delete this comment.")
            else:
                self.redirect("/login?error=comment does not exists")
        else:
            self.redirect("/login?error=comment does not exists")


class EditComment(BlogHandler):
    
    @login_required
    def get(self, post_id, comment_id):
        if post_id and comment_id:
            key = db.Key.from_path('Comment', int(comment_id),
                                   parent=blog_key())
            c = db.get(key)
            if not c:
                return self.redirect("/login?error=comment does not exists!")
            else:
                if c.user_id == self.user.key().id() and key and c:
                    self.render("editcomment.html", comment=c.comment)
                else:
                    self.redirect("/blog/" + post_id +
                                  "?error=You don't have access to edit this " +
                                  "comment.")
        else:
            return self.redirect("/login?error=comment does not exists!")

    @login_required
    def post(self, post_id, comment_id):
        """
        edit post (post_id) of a comment (comment_id)
        """
        
        comment = self.request.get('comment')

        if comment:
            if post_id and comment_id:
                key = db.Key.from_path('Comment',
                                       int(comment_id), parent=blog_key())
                c = db.get(key)
                if not c:
                    return self.redirect("/login?error=comment does not exists!")
                else:
                    if c.user_id == self.user.key().id():
                        c.comment = comment
                        c.put()
                        self.redirect('/blog/%s' % post_id)
                    else:
                        self.redirect("/blog/" + post_id +
                                      "?error=You don't have access to edit this " +
                                      "comment.")
            else:
                return self.redirect("login?error=comment does not exists")
        else:
            error = "subject and content, please!"
            self.render("editpost.html", subject=subject,
                        content=content, error=error)



def valid_username(username):
    USER_RE = re.compile(r"^[a-zA-Z0-9_-]{3,20}$")
    return username and USER_RE.match(username)


def valid_password(password):
    PASS_RE = re.compile(r"^.{3,20}$")
    return password and PASS_RE.match(password)
    

def valid_email(email):
    """
    validate email field
    if correct returns email
    """
    EMAIL_RE = re.compile(r'^[\S]+@[\S]+\.[\S]+$')
    return not email or EMAIL_RE.match(email)


class Signup(BlogHandler):
    def get(self):
        self.render("signup-form.html")

    def post(self):
        """
            Sign up validation.
        """
        have_error = False
        self.username = self.request.get('username')
        self.password = self.request.get('password')
        self.verify = self.request.get('verify')
        self.email = self.request.get('email')

        params = dict(username=self.username,
                      email=self.email)

        if not valid_username(self.username):
            params['error_username'] = "That's not a valid username."
            have_error = True

        if not valid_password(self.password):
            params['error_password'] = "That wasn't a valid password."
            have_error = True
        elif self.password != self.verify:
            params['error_verify'] = "Your passwords didn't match."
            have_error = True

        if not valid_email(self.email):
            params['error_email'] = "That's not a valid email."
            have_error = True

        if have_error:
            self.render('signup-form.html', **params)
        else:
            self.done()

    def done(self, *a, **kw):
        raise NotImplementedError


class Register(Signup):
    def done(self):
        """ 
        registration validation
        Make sure the user doesn't already exist
        """
        u = User.by_name(self.username)
        if u:
            msg = 'That user already exists.'
            self.render('signup-form.html', error_username=msg)
        else:
            u = User.register(self.username, self.password, self.email)
            u.put()

            self.login(u)
            self.redirect('/')


class Login(BlogHandler):
    def get(self):
        self.render('login-form.html', error=self.request.get('error'))

    def post(self):
        username = self.request.get('username')
        password = self.request.get('password')

        u = User.login(username, password)
        if u:
            self.login(u)
            self.redirect('/')
        else:
            msg = 'Invalid login'
            self.render('login-form.html', error=msg)


class Logout(BlogHandler):
    def get(self):
        self.logout()
        self.redirect('/')


app = webapp2.WSGIApplication([
                               ('/?', BlogFront),
                               ('/blog/([0-9]+)', PostPage),
                               ('/blog/newpost', NewPost),
                               ('/blog/deletepost/([0-9]+)', DeletePost),
                               ('/blog/editpost/([0-9]+)', EditPost),
                               ('/blog/deletecomment/([0-9]+)/([0-9]+)', DeleteComment),
                               ('/blog/editcomment/([0-9]+)/([0-9]+)', EditComment),
                               ('/signup', Register),
                               ('/login', Login),
                               ('/logout', Logout),
                               ('/not_found', NotFound),
                               ],
                              debug=True)

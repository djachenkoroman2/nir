from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse

from apps.research.models import ResearchProject
from apps.staff.models import AuthorBase


class Publication(models.Model):
    """Научная или учебно-методическая публикация."""

    class Kind(models.TextChoices):
        ARTICLE = 'article', 'статья'
        THESES = 'theses', 'тезисы доклада'
        MONOGRAPH = 'monograph', 'монография'
        MONOGRAPH_CHAPTER = 'monograph_chapter', 'глава в монографии'
        TEXTBOOK = 'textbook', 'учебник'
        STUDY_GUIDE = 'study_guide', 'учебное пособие'

    class VakCategory(models.TextChoices):
        NONE = '', 'нет'
        K1 = 'K1', 'К1'
        K2 = 'K2', 'К2'
        K3 = 'K3', 'К3'

    class Quartile(models.TextChoices):
        NONE = '', 'нет'
        Q1 = 'Q1', 'Q1'
        Q2 = 'Q2', 'Q2'
        Q3 = 'Q3', 'Q3'
        Q4 = 'Q4', 'Q4'

    kind = models.CharField('вид', max_length=20, choices=Kind.choices, default=Kind.ARTICLE)
    title = models.CharField('название', max_length=500)
    year = models.PositiveSmallIntegerField(
        'год', validators=[MinValueValidator(1900), MaxValueValidator(2100)]
    )
    source = models.CharField(
        'журнал / издательство / сборник', max_length=500, blank=True,
        help_text='Для статьи — журнал, для тезисов — сборник, для книги — издательство.',
    )
    volume = models.CharField('том', max_length=30, blank=True)
    issue = models.CharField('номер (выпуск)', max_length=30, blank=True)
    pages = models.CharField('страницы', max_length=30, blank=True, help_text='Например: 15–28 или 240 с.')
    doi = models.CharField('DOI', max_length=100, blank=True)
    url = models.URLField('ссылка', max_length=500, blank=True)

    vak = models.CharField('категория ВАК', max_length=2, choices=VakCategory.choices, blank=True)
    rinc = models.BooleanField('РИНЦ', default=False)
    rinc_core = models.BooleanField('ядро РИНЦ', default=False)
    scopus = models.BooleanField('Scopus', default=False)
    wos = models.BooleanField('Web of Science', default=False)
    quartile = models.CharField('квартиль', max_length=2, choices=Quartile.choices, blank=True)

    schools = models.ManyToManyField(
        'schools.ScientificSchool', verbose_name='научные школы', blank=True, related_name='publications',
        help_text='Научные направления, к которым относится публикация.',
    )
    project = models.ForeignKey(
        ResearchProject, verbose_name='НИОКР', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='publications', help_text='Если публикация — результат НИОКР.',
    )

    class Meta:
        verbose_name = 'публикация'
        verbose_name_plural = 'публикации'
        ordering = ['-year', 'title']

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('publications:publication_detail', args=[self.pk])

    def is_authored_by(self, teacher):
        return self.authors.filter(teacher=teacher).exists()

    @property
    def authors_display(self):
        return ', '.join(str(author) for author in self.authors.all())

    @property
    def indexing(self):
        """Список баз индексирования для вывода значками."""
        labels = []
        if self.vak:
            labels.append(f'ВАК {self.get_vak_display()}')
        if self.rinc_core:
            labels.append('ядро РИНЦ')
        elif self.rinc:
            labels.append('РИНЦ')
        if self.scopus:
            labels.append('Scopus')
        if self.wos:
            labels.append('WoS')
        if self.quartile:
            labels.append(self.quartile)
        return labels

    @property
    def imprint(self):
        """Выходные данные одной строкой: источник, год, том, номер, страницы."""
        parts = [self.source, str(self.year)]
        if self.volume:
            parts.append(f'Т. {self.volume}')
        if self.issue:
            parts.append(f'№ {self.issue}')
        if self.pages:
            parts.append(self.pages if 'с' in self.pages.lower() else f'С. {self.pages}')
        return '. — '.join(part for part in parts if part)


class PublicationAuthor(AuthorBase):
    publication = models.ForeignKey(
        Publication, verbose_name='публикация', on_delete=models.CASCADE, related_name='authors'
    )

    class Meta(AuthorBase.Meta):
        verbose_name = 'автор публикации'
        verbose_name_plural = 'авторы публикации'
        constraints = [
            models.UniqueConstraint(
                fields=['publication', 'teacher'], condition=models.Q(teacher__isnull=False),
                name='unique_publication_teacher',
            ),
            models.UniqueConstraint(
                fields=['publication', 'student'], condition=models.Q(student__isnull=False),
                name='unique_publication_student',
            ),
        ]
